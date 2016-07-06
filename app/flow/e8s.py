#!/usr/bin/env python
# encoding: utf-8

import requests
import json
import urllib

import datetime
import random
import time
from lxml import etree
from bs4 import BeautifulSoup

from app.constants import *
from app.flow.base import Flow as BaseFlow
from app.models import E8sAppRebot, Line
from datetime import datetime as dte
from app.utils import md5
from app import order_log, line_log


class Flow(BaseFlow):

    name = "e8s"

    def do_lock_ticket(self, order):
        rebot = order.get_lock_rebot()
        line = order.line
        data = {
                "drvDate": line.drv_date,
                "orderSourceId": '7',
                "userId": rebot.user_id,
                "stopId": line.d_city_id,
                "carryStaId": line.s_sta_id,
                "schId": line.bus_num,
                }
        jsonStr = {"carryPersonInfo": [], "ticketAmount":0}
        riders = order.riders
        tmp = {}
        ticketAmount = len(riders)
        jsonStr['ticketAmount'] = ticketAmount
        for i in riders:
            tmp = {
                "cardCode": i["id_number"],
                "insuranceFlag": "N",
                "cardName": i["name"],
                "mobile": i["telephone"],
            }
            jsonStr['carryPersonInfo'].append(tmp)
        data['jsonStr'] = json.dumps(jsonStr)
        order_log.info("[lock-start] order: %s,account:%s start  lock request", order.order_no, rebot.telephone)
        try:
            res = self.send_lock_request(order, rebot, data=data)
        except Exception, e:
            order_log.info("[lock-end] order: %s,account:%s lock request error %s", order.order_no, rebot.telephone,e)
            rebot.login()
            rebot.reload()
            res = self.send_lock_request(order, rebot, data=data)
        order_log.info("[lock-end] order: %s,account:%s lock request result : %s", order.order_no, rebot.telephone,res)
#             {"detail":{"orderCode":"160412010300100009","orderId":"439997"},"flag":"1"}
        lock_result = {
            "lock_info": res,
            "source_account": rebot.telephone,
            "pay_money": line.real_price()*order.ticket_amount,
        }
        if res['detail']:
            order_no = res["detail"]['orderCode']
            expire_time = dte.now()+datetime.timedelta(seconds=10*60)
            lock_result.update({
                "result_code": 1,
                "result_reason": "",
                "pay_url": "",
                "raw_order_no": order_no,
                "expire_datetime": expire_time,
                "lock_info": res
            })
        else:
            lock_result.update({
                "result_code": 0,
                "result_reason": res,
                "pay_url": "",
                "raw_order_no": "",
                "expire_datetime": None,
            })
        return lock_result

    def send_lock_request(self, order, rebot, data):
        """
        单纯向源站发请求
        """
        order_url = "http://m.e8s.com.cn/bwfpublicservice/saveStationSaveOrder.action"
        headers = rebot.http_header()
        r = rebot.http_post(order_url, data=data, headers=headers)
        ret = r.json()
        return ret

    def send_orderDetail_request(self, rebot, order=None, lock_info=None):
        detail_url = "http://m.e8s.com.cn/bwfpublicservice/getOrderInfo.action"
        headers = rebot.http_header()
#         rebot.login()
#         rebot.reload()
        data = {
            "orderId": order.lock_info['detail']['orderId'],
        }
        r = rebot.http_post(detail_url, data=data, headers=headers)
        ret = r.json()
        info = ret['detail']
        return {
            "order_status": str(info['ORDER_STATUS']),
            "pay_status": str(info['PAY_STATUS']),
            "pick_no": info['getTicketPwd'],
            "pick_code": info['getTicketCode'],
            "order_no": info['ORDER_CODE'],
            "order_date": info['ORDER_DATE'],
        }

    def do_refresh_issue(self, order):
        result_info = {
            "result_code": 0,
            "result_msg": "",
            "pick_code_list": [],
            "pick_msg_list": [],
        }
        rebot = E8sAppRebot.objects.get(telephone=order.source_account)
        order_log.info("[refresh_issue_start] order: %s,account:%s start orderDetail request", order.order_no, rebot.telephone)
        try:
            ret = self.send_orderDetail_request(rebot, order=order)
        except Exception, e:
            order_log.info("[refresh_issue_start] order: %s,account:%s start orderDetail request error %s", order.order_no, rebot.telephone,e)
            rebot.login()
            rebot.reload()
            ret = self.send_orderDetail_request(rebot, order=order)
        order_log.info("[refresh_issue_end] order: %s,account:%s orderDetail request result : %s", order.order_no, rebot.telephone,ret)

        if not order.raw_order_no:
            order.modify(raw_order_no=ret["order_no"])
        order_status = ret["order_status"]
        pay_status = ret["pay_status"]
        state = ''
        if pay_status == '1' and order_status in ('7','8','9'):
            state = '失败订单'
        if pay_status in ('7', '3', '2') and order_status == '1':
            state = "已购票"

        order_status_mapping = {
                "失败订单": "失败订单",
                "已购票": "购票成功",
                }

        if state in ["已购票"]: #"出票成功":
            pick_no, pick_code = ret["pick_no"], ret["pick_code"]
            dx_info = {
                "time": order.drv_datetime.strftime("%Y-%m-%d %H:%M"),
                "start": order.line.s_sta_name,
                "end": order.line.d_sta_name,
                "code": pick_code,
                "no": pick_no,
            }
            dx_tmpl = DUAN_XIN_TEMPL[SOURCE_E8S]
            code_list = ["%s|%s" % (pick_no, pick_code)]
            msg_list = [dx_tmpl % dx_info]
            result_info.update({
                "result_code": 1,
                "result_msg": order_status_mapping[state],
                "pick_code_list": code_list,
                "pick_msg_list": msg_list,
            })

        elif state in ["失败订单"]:#取消购票,购票失败,退票成功
            result_info.update({
                "result_code": 2,
                "result_msg": order_status_mapping[state],
            })
        return result_info

    def get_pay_page(self, order, valid_code="", session=None, pay_channel="alipay" ,**kwargs):
        rebot = order.get_lock_rebot()
        
        def _get_page(rebot):
            if order.status == STATUS_WAITING_ISSUE:
                pay_url = "http://www.bawangfen.cn/site/bwf/aliWapPay_doPay.action"
                headers = rebot.http_header()
                ret = self.send_orderDetail_request(rebot, order=order)
                order_status = ret["order_status"]
                pay_status = ret["pay_status"]
                order_date = ret["order_date"]

                if order_status in ('1', '3', '4', '5', '16') and pay_status == '1':
                    now = time.time()*1000
                    if now-order_date < 600000:
                        data = {
                            "payModel": "205",
                            "bwfUserId": rebot.user_id,
                            "orderId": order.lock_info['detail']['orderId'],
                            }
                        r = rebot.http_post(pay_url, data=data, headers=headers,allow_redirects=False)
#                         return {"flag": "html", "content": r.content}
                        location_url = r.headers.get('location', '')
                        if location_url:
                            return {"flag": "url", "content": location_url}
            return {"flag": "error", "content": "订单已支付成功或者失效"}
        if order.status in (STATUS_WAITING_LOCK, STATUS_LOCK_RETRY):
            self.lock_ticket(order)
        return _get_page(rebot)

    def do_refresh_line(self, line):
        result_info = {
            "result_msg": "",
            "update_attrs": {},
        }
        now = dte.now()
#         rebot = E8sAppRebot.get_one()
#         if not rebot.test_login_status():
#             rebot.login()
#             rebot.reload()
#         headers = rebot.http_header()
#         cookies = json.loads(rebot.cookies)

        headers = {
            "User-Agent": "Apache-HttpClient/UNAVAILABLE (java 1.4)",
            "Content-Type": "application/x-www-form-urlencoded; charset=UTF-8"
        }
        data = {
            "drvDate": line.drv_date,
            "rowNum": "10",
            "page": "1",
            "stopId": line.d_city_id,#"131000",
            "carryStaId": "-1"
        }

        url = "http://m.e8s.com.cn/bwfpublicservice/stationGetSchPlan.action"
        res = requests.post(url, data=data, headers=headers)
        res = res.json()
        if res["flag"] != "1":
            result_info.update(result_msg="error response", update_attrs={"left_tickets": 0, "refresh_datetime": now})
            return result_info

        update_attrs = {}
        for d in res["detail"]:
            if d['carrStaName'] != u"八王坟":
                continue
            drv_datetime = dte.strptime("%s %s" % (d["drvDate"], d["drvTime"]), "%Y-%m-%d %H:%M")
            line_id_args = {
                "s_city_name": line.s_city_name,
                "d_city_name": line.d_city_name,
                "bus_num": d["scheduleId"],
                "crawl_source": line.crawl_source,
                "drv_datetime": drv_datetime,
            }
            line_id = md5("%(s_city_name)s-%(d_city_name)s-%(drv_datetime)s-%(bus_num)s-%(crawl_source)s" % line_id_args)
            try:
                obj = Line.objects.get(line_id=line_id)
            except Line.DoesNotExist:
                continue
            info = {
                "full_price": float(d["fullPrice"]),
                "fee": 0,
                "left_tickets": int(d["seatAmount"]),
                "refresh_datetime": now,
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
