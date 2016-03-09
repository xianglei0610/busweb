#!/usr/bin/env python
# encoding: utf-8

import random
import requests
import json
import urllib
import datetime

from app.constants import *
from app.flow.base import Flow as BaseFlow
from app.models import Line, CqkyWebRebot, Order
from datetime import datetime as dte
from app.utils import md5, trans_js_str
from bs4 import BeautifulSoup
from app import order_log


class Flow(BaseFlow):

    name = "cqky"

    def do_lock_ticket(self, order):
        lock_result = {
            "lock_info": {},
            "source_account": order.source_account,
            "result_code": 0,
            "result_reason": "",
            "pay_url": "",
            "raw_order_no": "",
            "expire_datetime": "",
            "pay_money": 0,
        }
        with CqkyWebRebot.get_and_lock(order) as rebot:
            line = order.line

            is_login = rebot.test_login_status()
            # 未登录
            if not is_login:
                lock_result.update({
                    "result_code": 2,
                    "source_account": rebot.telephone,
                    "result_reason": u"账号未登录",
                })
                return lock_result

            res = self.request_station_status(line, rebot)
            if res["success"]:
                pass
            else:
                res = self.request_add_shopcart(order, rebot)
                if res["success"]:
                    print self.request_lock(order, rebot)
                else:
                    lock_result.update({
                        "result_code": 0,
                        "result_reason": "add_shopcat error. %s" % res["msg"],
                        "source_account": rebot.telephone,
                    })
            return lock_result

    def request_lock(self, order, rebot):
        base_url = "http://www.96096kp.com/CommitGoods.aspx"
        headers = {
            "User-Agent": rebot.user_agent,
            "Referer": "http://www.96096kp.com/TicketMain.aspx",
            "Origin": "http://www.96096kp.com",
            "Content-Type": "application/x-www-form-urlencoded; charset=UTF-8",
        }
        cookies = json.loads(rebot.cookies)
        params ={
            "ctl00$FartherMain$NavigationControl1$CustRBList": """{"Moblie":"15575101324","ID":"552bcc59-e1ea-11e5-960a-78e3b50bbe0f","Email":"","Name":"罗军平","CerType":"1","CerNo":"431021199004165616","Addr":"","Notes":"默认"}""",
            "ctl00$FartherMain$NavigationControl1$o_CustomerName": order.contact_info["name"],
            "ctl00$FartherMain$NavigationControl1$o_Mobele": rebot.telephone,
            "ctl00$FartherMain$NavigationControl1$o_IdType": 1,
            "ctl00$FartherMain$NavigationControl1$o_IdCard": order.contact_info["id_number"],
            "ctl00$FartherMain$NavigationControl1$o_IdCardConfirm": order.contact_info["id_number"],
            "ctl00$FartherMain$NavigationControl1$radioListPayType": "OnlineAliPay,支付宝在线支付",
            "ctl00$FartherMain$NavigationControl1$o_Email": "",
            "ctl00$FartherMain$NavigationControl1$ContactAddress": "",
            "ctl00$FartherMain$NavigationControl1$o_Memo": "",
            "ctl00$FartherMain$NavigationControl1$hideIsSubmit": "true",
        }
        r = requests.post(base_url,
                          data=urllib.urlencode(params),
                          headers=headers,
                          cookies=cookies)
        return r.content

    def request_get_shoptcart(self, rebot):
        """
        获取购物车条目
        """
        base_url = "http://www.96096kp.com/UserData/ShopCart.aspx"
        headers = {
            "User-Agent": rebot.user_agent,
            "Referer": "http://www.96096kp.com/TicketMain.aspx",
            "Origin": "http://www.96096kp.com",
            "Content-Type": "application/x-www-form-urlencoded; charset=UTF-8",
        }
        cookies = json.loads(rebot.cookies)
        params = {
            "cmd": "getCartItemList",
        }
        r = requests.post(base_url,
                          data=urllib.urlencode(params),
                          headers=headers,
                          cookies=cookies)
        return r.json()


    def request_add_shopcart(self, order, rebot):
        """
        加入购物车
        """
        line = order.line
        base_url = "http://www.96096kp.com/UserData/ShopCart.aspx"
        headers = {
            "User-Agent": rebot.user_agent,
            "Referer": "http://www.96096kp.com/TicketMain.aspx",
            "Origin": "http://www.96096kp.com",
            "Content-Type": "application/x-www-form-urlencoded; charset=UTF-8",
        }
        cookies = json.loads(rebot.cookies)
        params = {
            "classInfo": line.extra_info["raw_info"],
            "drBusStationCode": line.s_sta_id,
            "drBusStationName": line.s_sta_name,
            "ticketHalfCount": 0,
            "ticketFullCount": order.ticket_amount,
            "ticketChildCount": 0,
            "cmd": "buyTicket",
        }
        r = requests.post(base_url,
                          data=urllib.urlencode(params),
                          headers=headers,
                          cookies=cookies)
        return json.loads(trans_js_str(r.content))

    def request_station_status(self, line, rebot):
        """
            车站状态
        """
        base_url = "http://www.96096kp.com/UserData/UserCmd.aspx"
        params = {
            "SchStationCode": line.s_sta_id,
            "SchStationName": line.s_sta_name,
            "cmd": "GetStationStatus",
        }
        headers = {
            "User-Agent": rebot.user_agent,
            "Referer": "http://www.96096kp.com/TicketMain.aspx",
            "Origin": "http://www.96096kp.com",
            "Content-Type": "application/x-www-form-urlencoded; charset=UTF-8",
        }
        cookies = json.loads(rebot.cookies)
        r = requests.post(base_url, data=urllib.urlencode(params), headers=headers, cookies=cookies)
        return json.loads(trans_js_str(r.content))

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
        rebot = TCWebRebot.objects.get(telephone=order.source_account)
        ret = self.send_order_request(rebot, order=order)
        state = ret["state"]
        if state == "出票中":
            result_info.update({
                "result_code": 4,
                "result_msg": state,
            })
        elif state=="出票成功":
            pass
        return result_info

    def get_pay_page(self, order, valid_code="", session=None, pay_channel="alipay" ,**kwargs):
        rebot = CqkyWebRebot.objects.get(telephone=order.source_account)
        if valid_code:
            login_url= "http://www.96096kp.com/UserData/UserCmd.aspx"
            info = json.loads(session["pay_login_info"])
            headers = info["headers"]
            cookies = info["cookies"]
            headers = {
                "User-Agent": headers.get("User-Agent", "") or rebot.user_agent,
                "Referer": "http://www.96096kp.com/CusLogin.aspx",
                "Origin": "http://www.96096kp.com",
                "Content-Type": "application/x-www-form-urlencoded; charset=UTF-8",
            }
            params = {
                "loginID": rebot.telephone,
                "loginPwd": rebot.password,
                "getInfo": 1,
                "loginValid": valid_code,
                "cmd": "Login",
            }
            r = requests.post(login_url, data=urllib.urlencode(params), headers=headers, cookies=cookies)
            cookies.update(dict(r.cookies))
            rebot.modify(cookies=json.dumps(cookies))

        is_login = rebot.test_login_status()
        if is_login:
            if order.status == STATUS_LOCK_RETRY:
                self.lock_ticket(order)
            if order.status == STATUS_WAITING_ISSUE:
                return {"flag": "url", "content": order.pay_url}
        else:
            login_form = "http://www.96096kp.com/CusLogin.aspx"
            valid_url = "http://www.96096kp.com/ValidateCode.aspx"
            headers = {"User-Agent": random.choice(BROWSER_USER_AGENT)}
            r = requests.get(login_form, headers=headers)
            data = {
                "cookies": dict(r.cookies),
                "headers": headers,
                "valid_url": valid_url,
            }
            session["pay_login_info"] = json.dumps(data)
            return {"flag": "input_code", "content": ""}

    def do_refresh_line(self, line):
        result_info = {
            "result_msg": "",
            "update_attrs": {},
        }
        line_url = "http://m.ly.com/bus/BusJson/BusSchedule"
        params = dict(
            Departure=line.s_city_name,
            Destination=line.d_city_name,
            DepartureDate=line.drv_date,
            DepartureStation="",
            DptTimeSpan=0,
            HasCategory="true",
            Category="0",
            SubCategory="",
            ExParms="",
            Page="1",
            PageSize="1025",
            BookingType="0"
        )
        headers = {
            "User-Agent": random.choice(BROWSER_USER_AGENT),
            "Content-Type": "application/x-www-form-urlencoded",
        }
        r = requests.post(line_url, data=urllib.urlencode(params), headers=headers)
        res = r.json()
        res = res["response"]
        now = dte.now()
        if res["rspCode"] != "0000":
            result_info.update(result_msg="error response", update_attrs={"left_tickets": 0, "refresh_datetime": now})
            return result_info

        update_attrs = {}
        for d in res["body"]["schedule"]:
            drv_datetime = dte.strptime("%s %s" % (d["dptDate"], d["dptTime"]), "%Y-%m-%d %H:%M")
            line_id_args = {
                "s_city_name": line.s_city_name,
                "d_city_name": line.d_city_name,
                "bus_num": d["coachNo"],
                "crawl_source": line.crawl_source,
                "drv_datetime": drv_datetime,
            }
            line_id = md5("%(s_city_name)s-%(d_city_name)s-%(drv_datetime)s-%(bus_num)s-%(crawl_source)s" % line_id_args)
            try:
                obj = Line.objects.get(line_id=line_id)
            except Line.DoesNotExist:
                continue
            info = {
                "full_price": float(d["ticketPrice"]),
                "fee": 0,
                "left_tickets": int(d["ticketLeft"]),
                "refresh_datetime": now,
                "extra_info": {},
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
