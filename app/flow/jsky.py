#!/usr/bin/env python
# encoding: utf-8

import random
import requests
import datetime
import json
import urlparse
import re

from lxml import etree
from bs4 import BeautifulSoup
from app.constants import *
from app.flow.base import Flow as BaseFlow
from app.models import JskyAppRebot, Line
from datetime import datetime as dte
from app.utils import md5
from app import order_log


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
                    "IDCard": r["id_number"],
                    "IDType": 1,
                    "passengerType": 0
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
                    "arrStation": line.destination.station_name,
                    "childPrice": line.half_price,
                    "coachNo": line.bus_num,
                    "coachType": line.vehicle_type,
                    "departure": line.starting.city_name,
                    "destination": line.destination.city_name,
                    "dptDate": line.drv_date,
                    "dptDateTime": "%s %s:00.000" % (line.drv_date, line.drv_time),
                    "dptStation": line.starting.station_name,
                    "dptTime": line.drv_time,
                    "remainChildNum": "0",
                    "ticketFee": str(line.fee),
                    "ticketPrice": str(line.full_price),
                },
                "totalAmount": str(line.real_price()*order.ticket_amount),
            }
            data = rebot.post_data_templ("createbusorder", body)
            ret = self.send_lock_request(order, rebot, data=data)
            res = ret["response"]
            lock_result = {
                "lock_info": ret,
                "source_account": rebot.telephone,
                "pay_money": line.real_price()*order.ticket_amount,
            }
            if res["header"]["rspCode"] == "0000":
                lock_result.update({
                    "result_code": 1,
                    "result_reason": "",
                    "pay_url": "",
                    "raw_order_no": "",
                    "expire_datetime": res["body"]["payExpireDate"],
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

    def send_order_request(self, order, rebot):
        detail_url = "http://api.jskylwsp.cn/ticket-interface/rest/order/getBusOrderDetail"
        headers = rebot.http_header()
        r = requests.get(detail_url, headers=headers, =json.loads(rebot.cookies))
        soup = BeautifulSoup(r.content, "lxml")
        state_element =soup.select(".orderDetail_state")[0]
        state = state_element.get_text().strip()
        order_no = soup.find_all(text=re.compile(u"订单号"))[0].split(u"订单号：")[1]

        pick_no, pick_code = "", ""
        for ele in soup.select(".ticket_info .mtop-10"):
            label = ele.label.get_text().strip()
            span = ele.span.get_text().strip()
            if label == u"取票号：":
                pick_no = span
            elif label == u"取票密码：":
                pick_code = span

        return {
            "order_no": order_no or order.raw_order_no,
            "state": state,
            "code_list": ["%s|%s" % (pick_no, pick_code)],
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
        rebot = CBDRebot.objects.get(telephone=order.source_account)
        ret = self.send_order_request(order, rebot)
        if not order.raw_order_no:
            order.modify(raw_order_no=ret["order_no"])
        state = ret["state"]
        if "出票成功" in state:
            msg_list = []
            dx_tmpl = DUAN_XIN_TEMPL[SOURCE_CBD]
            for info in ret["code_list"]:
                no, code = info.split("|")
                dx_info = {
                    "time": order.drv_datetime.strftime("%Y-%m-%d %H:%M"),
                    "start": order.line.starting.station_name,
                    "end": order.line.destination.station_name,
                    #"amount": order.ticket_amount,
                    "code": code,
                    "no": no,
                    "raw_order": order.raw_order_no,
                }
                msg_list.append(dx_tmpl % dx_info)
            result_info.update({
                "result_code": 1,
                "result_msg": state,
                "pick_code_list": ret["code_list"],
                "pick_msg_list": msg_list,
            })
        elif "出票中" in state and "已支付" in state:
            result_info.update({
                "result_code": 4,
                "result_msg": state,
            })
        elif "已取消"  in state:
            result_info.update({
                "result_code": 2,
                "result_msg": state,
            })
        elif "已退款"  in state:
            result_info.update({
                "result_code": 3,
                "result_msg": state,
            })
        return result_info

    def do_refresh_line(self, line):
        result_info = {
            "result_msg": "",
            "update_attrs": {},
        }
        line_url = "http://m.chebada.com/Schedule/GetBusSchedules"
        params = dict(
            departure=line.starting.city_name,
            destination=line.destination.city_name,
            departureDate=line.drv_date,
            page="1",
            pageSize="1025",
            hasCategory="true",
            category="0",
            dptTimeSpan="0",
            bookingType="0",
        )
        ua = random.choice(BROWSER_USER_AGENT)
        headers = {"User-Agent": ua}
        r = requests.post(line_url, data=params, headers=headers)
        ret = r.json()
        res = ret["response"]
        now = dte.now()
        if int(res["header"]["rspCode"]) != 0:
            result_info.update(result_msg="error response", update_attrs={"left_tickets": 0, "refresh_datetime": now})
            return result_info

        update_attrs = {}
        for d in res["body"]["scheduleList"]:
            line_id = md5("%s-%s-%s-%s-%s-cbd" % (d["departure"],
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
                "fee": float(d["ticketFee"]),
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

    def check_login_by_resp(self, rebot, resp):
        if urlparse.urlsplit(resp.url).path=="/Account/Login":
            for i in range(2):
                if rebot.login() == "OK":
                    return "relogined"
            rebot.modify(is_active=False)
            return "fail"
        try:
            ret = json.loads(resp.content)
            if ret["response"]["header"]["rspCode"] == "3100":
                for i in range(2):
                    if rebot.login() == "OK":
                        return "relogined"
                rebot.modify(is_active=False)
                return "fail"
        except:
            pass
        return "logined"

    def get_pay_page(self, order, valid_code="", session=None, pay_channel="wy" ,**kwargs):
        return {"flag": "url", "content": order.pay_url}
