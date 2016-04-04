#!/usr/bin/env python
# encoding: utf-8

import requests
import json
import urllib

import datetime

from app.constants import *
from app.flow.base import Flow as BaseFlow
from app.models import JskyAppRebot, Line, JskyWebRebot
from datetime import datetime as dte
from app.utils import md5
from bs4 import BeautifulSoup


class Flow(BaseFlow):

    name = "jsky"

    def do_lock_ticket(self, order):
        with JskyAppRebot.get_and_lock(order) as rebot:
            line = order.line
            rider_info = []
            for r in order.riders:
                rider_info.append({
                    "name": r["name"],
                    "mobileNo": r["telephone"],
                    "idCard": r["id_number"],
                    "idType": 1,
                })
            body = {
                "activityId": "0",
                "activityType": "",
                "childCount": "0",
                "contactInfo": {
                    "name": order.contact_info["name"],
                    "mobileNo": order.contact_info["telephone"],
                    "idCard": order.contact_info["id_number"],
                    "idType": "0",
                },
                "count": str(order.ticket_amount),
                "insuranceAmount": "0.0",
                "insuranceId": "null",
                "memberId": rebot.member_id,
                "passengersInfo": rider_info,
                "reductAmount": "0",
                "sessionId": "",
                "ticketsInfo": {
                    "arrStation": line.d_sta_name,
                    "childPrice": line.half_price,
                    "coachNo": line.bus_num,
                    "coachType": line.vehicle_type,
                    "departure": line.s_city_name,
                    "destination": line.d_city_name,
                    "dptDate": line.drv_date,
                    "dptDateTime": "%s %s:00.000" % (line.drv_date, line.drv_time),
                    "dptStation": line.s_sta_name,
                    "dptTime": line.drv_time,
                    "remainChildNum": "0",
                    "ticketFee": str(line.fee),
                    "ticketPrice": str(line.full_price),
                },
                "totalAmount": str(line.real_price()*order.ticket_amount),
            }
            data = rebot.post_data_templ("createbusorder", body)
            res = self.send_lock_request(order, rebot, data=data)

            lock_result = {
                "lock_info": res,
                "source_account": rebot.telephone,
                "pay_money": line.real_price()*order.ticket_amount,
            }
            if res["header"]["rspCode"] == "0000":
                detail = self.send_order_request(rebot, lock_info=res)
                expire_time = dte.now()+datetime.timedelta(seconds=20*60)
                lock_result.update({
                    "result_code": 1,
                    "result_reason": "",
                    "pay_url": "",
                    "raw_order_no": detail["order_no"],
                    "expire_datetime": expire_time,

                })
            else:
                lock_result.update({
                    "result_code": 0,
                    "result_reason": res["header"]["rspCode"],
                    "pay_url": "",
                    "raw_order_no": "",
                    "expire_datetime": None,
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
        elif state=="出票失败":
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
            r = requests.post(pay_url,
                              data=data,
                              headers=headers,
                              cookies=json.loads(rebot.cookies),
                              allow_redirects=False)
            content = r.content.decode("gbk")
            soup = BeautifulSoup(r.content, "lxml")
            if soup.select("#mobile") and soup.select("#password"):
                rebot.login()
            else:
                gateway = soup.find("a").get("href")
                for s in gateway.split("?")[1].split("&"):
                    k, v = s.split("=")
                    if k == "out_trade_no":
                        if order.pay_order_no != v:
                            order.modify(pay_order_no=v)
                        break
                return {"flag": "url", "content": gateway}
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
            drv_datetime = dte.strptime("%s %s" % (d["dptDate"], d["dptTime"]), "%Y-%m-%d %H:%M")
            line_id_args = {
                "s_city_name": line.s_city_name,
                "d_city_name": line.d_city_name,
                #"bus_num": d["coachNo"],
                "s_sta_name": d["dptStation"],
                "d_sta_name": d["arrStation"],
                "crawl_source": line.crawl_source,
                "drv_datetime": drv_datetime,
            }
            line_id = md5("%(s_city_name)s-%(d_city_name)s-%(drv_datetime)s-%(s_sta_name)s-%(d_sta_name)s-%(crawl_source)s" % line_id_args)
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
