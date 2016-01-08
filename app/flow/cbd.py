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
from collections import OrderedDict
from app.constants import *
from app.flow.base import Flow as BaseFlow
from app.models import CBDRebot, Line
from datetime import datetime as dte
from app.utils import chinese_week_day, md5
from app import order_log

class Flow(BaseFlow):

    name = "cbd"

    def do_lock_ticket(self, order):
        with CBDRebot.get_and_lock(order) as rebot:
            line = order.line
            ticket_info = line.extra_info["raw_info"]
            ticket_info.update(week=chinese_week_day(line.drv_datetime), optionType=1)
            rider_info = []
            for r in order.riders:
                rider_info.append({
                    "name": r["name"],
                    "mobileNo": r["telephone"],
                    "IDCard": r["id_number"],
                    "IDType": 1,
                    "passengerType": 0
                })
            data  = OrderedDict(
                ticketsInfo=ticket_info,
                dptStationCode=ticket_info["dptStationCode"],
                passengersInfo=rider_info,
                contactInfo={
                    "name": order.contact_info["name"],
                    "mobileNo": order.contact_info["telephone"],
                    "IDCard": order.contact_info["id_number"],
                    "IDType": 1,
                    "passengerType": 0
                },
                insuranceId="",
                insuranceAmount="NaN",
                totalAmount=str(line.real_price()*order.ticket_amount),
                count=order.ticket_amount,
                reductAmount="0",
                activityType="",
                activityId="0",
                couponCode="",
                couponAmount="0"
            )

            ret = self.send_lock_request(order, rebot, data=data)
            res = ret["response"]
            lock_result = {
                "lock_info": {"raw_return": ret},
                "source_account": rebot.telephone,
                "pay_money": 0,
            }
            if int(res["header"]["rspCode"]) == 0:
                pay_url = res["body"]["PayUrl"]
                pay_ret = self.send_pay_request(pay_url, rebot)
                lock_result.update({
                    "result_code": 1,
                    "result_reason": "",
                    "pay_url": pay_url,
                    "raw_order_no": "",
                    "expire_datetime": pay_ret["expire_time"],
                    "pay_money": pay_ret["total_price"],
                })
                lock_result["lock_info"].update(order_detail_url=pay_ret["detail_url"])
            else:
                lock_result.update({
                    "result_code": 0,
                    "result_reason": res["header"]["rspDesc"],
                    "pay_url": "",
                    "raw_order_no": "",
                    "expire_datetime": None,
                })
            return lock_result

    def send_lock_request(self, order, rebot, data):
        """
        单纯向源站发请求
        """
        order_url = "http://m.chebada.com/Order/CreateOrder"
        headers = {
            "User-Agent": rebot.user_agent,
            "Content-Type": "application/json",
        }
        for i in range(2):
            r = requests.post(order_url, data=json.dumps(data), headers=headers, cookies=json.loads(rebot.cookies))
            ret = r.json()
            if self.check_login_by_resp(rebot, r) != "relogined":
                break
        return ret

    def send_pay_request(self, pay_url, rebot):
        for i in range(2):
            headers = {
                "User-Agent": rebot.user_agent,
            }
            r = requests.get(pay_url, headers=headers, cookies=json.loads(rebot.cookies))
            if self.check_login_by_resp(rebot, r) != "relogined":
                break
        sel = etree.HTML(r.content)
        detail_url = sel.xpath("//a[@class='page-back touchable']/@href")[0]
        total_price = sel.xpath("//span[@class='price']/text()")[0].split(u"元")[0]
        expire_time = dte.now()+datetime.timedelta(seconds=20*60)
        return {
            "detail_url": detail_url,
            "total_price": float(total_price),
            "expire_time": expire_time,
        }

    def send_order_request(self, order, rebot):
        detail_url = order.lock_info["order_detail_url"]
        for i in range(2):
            headers = {"User-Agent": rebot.user_agent}
            r = requests.get(detail_url, headers=headers, cookies=json.loads(rebot.cookies))
            if self.check_login_by_resp(rebot, r) != "relogined":
                break
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
