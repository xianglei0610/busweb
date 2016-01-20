#!/usr/bin/env python
# encoding: utf-8

import requests
import json
import urllib
import urlparse

from app.constants import *
from app.flow.base import Flow as BaseFlow
from app.models import Line, BabaWebRebot
from datetime import datetime as dte
from app.utils import md5
from bs4 import BeautifulSoup


class Flow(BaseFlow):

    name = "baba"

    def check_login_status(self, resp):
        result = urlparse.urlparse(resp.url)
        if "login" in result.path:
            return 0
        return 1

    def do_lock_ticket(self, order):
        lock_result = {
            "lock_info": {},
            "source_account": '',
            "result_code": 0,
            "result_reason": "",
            "pay_url": "",
            "raw_order_no": "",
            "expire_datetime": "",
            "pay_money": 0,
        }
        with BabaWebRebot.get_and_lock(order) as rebot:
            line = order.line
            form_url = "http://www.bababus.com/baba/order/writeorder.htm"
            params = {
                "sbId": line.extra_info["sbId"],
                "stId": line.extra_info["stId"],
                "depotId": line.extra_info["depotId"],
                "busId": line.bus_num,
                "leaveDate": line.drv_date,
                "beginStationId": line.s_sta_id,
                "endStationId": line.d_sta_id,
                "endStationName": line.d_sta_name,
            }
            r = requests.get("%s?%s" %(form_url,urllib.urlencode(params)),
                             headers={"User-Agent": rebot.user_agent},
                             cookies=json.loads(rebot.cookies))

            # 未登录
            if not self.check_login_status(r):
                lock_result.update({
                    "result_code": 2,
                    "source_account": rebot.telephone,
                    "result_reason": "账号未登录",
                })
                return lock_result

            soup = BeautifulSoup(r.content, "lxml")
            wrong_info = soup.select(".wrong_body .wrong_inf")
            # 订单填写页获取错误
            if wrong_info:
                inf = soup.select(".wrong_body .wrong_inf")[0].get_text()
                tip = soup.select(".wrong_body .wrong_tip")[1].get_text()
                lock_result.update({
                    "result_code": 2,
                    "source_account": rebot.telephone,
                    "result_reason": "%s %s" % (inf, tip),
                })
                return lock_result


    def send_lock_request(self, order, rebot, data):
        """
        单纯向源站发请求
        """
        order_url = "http://api.jskylwsp.cn/ticket-interface/rest/order/createbusorder"
        headers = rebot.http_header()
        r = requests.post(order_url, data=json.dumps(data), headers=headers)
        ret = r.json()
        return ret

    def send_order_request(self, rebot, order=None, lock_info=None):
        detail_url = "http://api.jskylwsp.cn/ticket-interface/rest/order/getBusOrderDetail"
        headers = rebot.http_header()
        body = {
            "memberId": rebot.member_id,
            "orderId": order.lock_info["body"]["orderId"] if order else lock_info["body"]["orderId"],
        }
        data = rebot.post_data_templ("getbusorderdetail", body)
        r = requests.post(detail_url, headers=headers, data=json.dumps(data))
        ret = r.json()
        pick_info = ret["body"]["getTicketInfos"]
        return {
            "order_no": ret["body"]["shortSerialId"],
            "state": ret["body"]["orderStateName"],
            "code_list": ["%s|%s" % (pick_info["getTicketNo"], pick_info["getTicketPassWord"])],
            "msg_list": [pick_info["getTicketInfo"]],
        }

    def do_refresh_issue(self, order):
        result_info = {
            "result_code": 0,
            "result_msg": "",
            "pick_code_list": [],
            "pick_msg_list": [],
        }
        if not self.need_refresh_issue(order):
            result_info.update(result_msg="状态未变化")
            return result_info
        rebot = JskyAppRebot.objects.get(telephone=order.source_account)
        ret = self.send_order_request(rebot, order=order)
        if not order.raw_order_no:
            order.modify(raw_order_no=ret["order_no"])
        state = ret["state"]
        if state=="出票成功":
            result_info.update({
                "result_code": 1,
                "result_msg": state,
                "pick_code_list": ret["code_list"],
                "pick_msg_list": ret["msg_list"],
            })
        elif state=="出票中":
            result_info.update({
                "result_code": 4,
                "result_msg": state,
            })
        elif state=="已取消":
            result_info.update({
                "result_code": 2,
                "result_msg": state,
            })
        return result_info

    def get_pay_page(self, order, valid_code="", session=None, pay_channel="alipay" ,**kwargs):
        rebot = JskyWebRebot.get_one()

        pay_url = "http://www.jskylwsp.com/Order/OrderPay"
        data = {
            "OrderSerialid": order.lock_info["body"]["orderSerialId"],
            "PayType": "1",
            "defaultBank": "",
            "MilliSecond": "900",
            "payType": "on",
        }
        for i in range(2):
            headers = {
                "User-Agent": rebot.user_agent,
                "Content-Type": "application/x-www-form-urlencoded",
                "Accept-Language": "zh-CN,zh;q=0.8,zh-TW;q=0.6,en;q=0.4",
            }
            data = urllib.urlencode(data)
            r = requests.post(pay_url, data=data, headers=headers, cookies=json.loads(rebot.cookies))
            content = r.content.decode("gbk")
            soup = BeautifulSoup(r.content, "lxml")
            if soup.select("#mobile") and soup.select("#password"):
                rebot.login()
            else:
                break
        return {"flag": "html", "content": content}

    def do_refresh_line(self, line):
        result_info = {
            "result_msg": "",
            "update_attrs": {},
        }
        line_url = "http://api.jskylwsp.cn/ticket-interface/rest/query/getbusschedule"
        rebot = JskyAppRebot.get_one()
        body = {
            "departure": line.s_city_name,
            "destination": line.d_city_name,
            "dptDate": line.drv_date,
            "pageIndex": 1,
            "pageSize": 1025,
        }
        data = rebot.post_data_templ("getbusschedule", body)
        headers = rebot.http_header()
        r = requests.post(line_url, data=json.dumps(data), headers=headers)
        res = r.json()
        now = dte.now()
        if res["header"]["rspCode"] != "0000":
            result_info.update(result_msg="error response", update_attrs={"left_tickets": 0, "refresh_datetime": now})
            return result_info

        update_attrs = {}
        for d in res["body"]["scheduleList"]:
            line_id = md5("%s-%s-%s-%s-%s-jsky" % (d["departure"],
                                                d["destination"],
                                                d["dptStation"],
                                                d["arrStation"],
                                                d["dptDateTime"]))
            try:
                obj = Line.objects.get(line_id=line_id)
            except Line.DoesNotExist:
                continue
            extra_info = obj.extra_info
            extra_info.update(raw_info=d)
            info = {
                "full_price": d["ticketPrice"],
                "fee": 0,
                "left_tickets": d["ticketLeft"],
                "refresh_datetime": now,
                "extra_info": extra_info,
            }
            if line_id == line.line_id:
                update_attrs = info
            else:
                obj.update(**info)
        if not update_attrs:
            result_info.update(result_msg="no line info", update_attrs={"left_tickets": 0, "refresh_datetime": now})
        else:
            result_info.update(result_msg="ok", update_attrs=update_attrs)
        return result_info
