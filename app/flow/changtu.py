#!/usr/bin/env python
# encoding: utf-8

import random
import requests
import json
import urllib
import datetime
import time

from app.constants import *
from app.flow.base import Flow as BaseFlow
from app.models import ChangtuWebRebot
from datetime import datetime as dte
from bs4 import BeautifulSoup


class Flow(BaseFlow):

    name = "changtu"

    def do_lock_ticket_web(self, order, valid_code=""):
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
        with ChangtuWebRebot.get_and_lock(order) as rebot:
            line = order.line
            is_login = rebot.test_login_status()
            # 未登录
            if not is_login:
                lock_result.update({ "result_code": 2,
                    "source_account": rebot.telephone,
                    "result_reason": u"账号未登录",
                })
                return lock_result

            form_url = "http://www.changtu.com/trade/order/toFillOrderPage.htm"
            ticket_type =line.extra_info["ticketTypeStr"].split(",")[0]
            sta_city_id, s_pinyin = line.s_city_id.split("|")
            d_end_type, d_pinyin, end_city_id = line.d_city_id.split("|")
            params = dict(
                stationMapId=line.extra_info["stationMapId"],
                planId=line.extra_info["id"],
                stCityId=sta_city_id,
                endTypeId=d_end_type,
                endCityId=end_city_id,
                stationId=line.s_sta_id,
                ticketType=ticket_type,
                schSource=0,
            )
            cookies = json.loads(rebot.cookies)
            r = requests.get("%s?%s" %(form_url,urllib.urlencode(params)),
                             headers={"User-Agent": rebot.user_agent},
                             cookies=cookies)
            soup = BeautifulSoup(r.content, "lxml")
            token = soup.select("#token")[0].get("value")
            passenger_info = {}
            for i, r in enumerate(order.riders):
                passenger_info.update({
                    "ticketInfo_%s" % i: "1♂%s♂%s♂0♂♂N" % (r["name"], r["id_number"])
                })

            params = {
                "refUrl": "http://www.changtu.com/",
                "stationMapId": line.extra_info["stationMapId"],
                "planId": line.extra_info["id"],
                "planDate": line.drv_date,
                "receUserName": order.contact_info["name"],
                "receUserCardCode": order.contact_info["id_number"],
                "receUserContact": rebot.telephone,
                "orderCount": 1,        # 这个???
                "arMoney": order.order_price,
                "passengerStr": json.dumps(passenger_info),
                "yhqMoney": 0,
                "yhqId": "",
                "tickType": ticket_type,
                "saveReceUserFlag": "N",
                "endTypeId": d_end_type,
                "endId": end_city_id,
                "startCityId": sta_city_id,
                "redPayMoney": "0.00",
                "redPayPwd": "",
                "reduceActionId": "",
                "reduceMoney": "",
                "orderModelId": 1,
                "fkReserveSchId": "",
                "reserveNearbyFlag": "N",
                "stationId": line.s_sta_id,
                "actionFlag": 2,
                "t": token,
                "fraud": json.dumps({"verifyCode": valid_code}),
            }
            ret = self.send_lock_request_web(order, rebot, submit_data)
            flag = int(ret["flag"])
            if flag == 1:
                expire_time = dte.now()+datetime.timedelta(seconds=10*60)
                lock_result.update({
                    "result_code": 1,
                    "result_reason": "",
                    "pay_url": "",
                    "raw_order_no": "",
                    "expire_datetime": expire_time,
                    "source_account": rebot.telephone,
                    "lock_info": ret,
                })
            else:
                fail_code = ret.get("failReason", "")
                if fail_code == "13":   # 要输字母验证码
                    lock_result.update({
                        "result_code": 2,
                        "result_reason": str(ret),
                        "source_account": rebot.telephone,
                        "lock_info": ret,
                    })
                else:
                    lock_result.update({
                        "result_code": 0,
                        "result_reason": str(ret),
                        "pay_url": "",
                        "raw_order_no": "",
                        "expire_datetime": None,
                        "source_account": rebot.telephone,
                        "lock_info": ret,
                    })
            return lock_result

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
        with ChangtuWebRebot.get_and_lock(order) as rebot:
            line = order.line
            is_login = rebot.test_login_status()
            # 未登录
            if not is_login:
                lock_result.update({ "result_code": 2,
                    "source_account": rebot.telephone,
                    "result_reason": u"账号未登录",
                })
                return lock_result
            form_url = "http://m.changtu.com/order/fillInOrder.htm"
            sta_city_id, s_pinyin = line.s_city_id.split("|")
            d_end_type, d_pinyin, end_city_id = line.d_city_id.split("|")
            ticket_type =line.extra_info["ticketTypeStr"].split(",")[0]
            params = dict(
                stationMapId=line.extra_info["stationMapId"],
                planId=line.extra_info["id"],
                stCityId=sta_city_id,
                endTypeId=d_end_type,
                endCityId=end_city_id,
                stationId=line.s_sta_id,
                ticketType=ticket_type,
                schSource=0,
            )
            cookies = json.loads(rebot.cookies)
            r = requests.get("%s?%s" %(form_url,urllib.urlencode(params)),
                             headers={"User-Agent": rebot.user_agent},
                             cookies=cookies)

            soup = BeautifulSoup(r.content, "lxml")
            token = soup.select("#token")[0].get("value")

            passenger_info = {}
            for i, r in enumerate(order.riders):
                passenger_info.update({
                    "ticketInfo_%s" % i: "1♂%s♂%s♂0♂♂N" % (r["name"], r["id_number"])
                })

            submit_data = dict(
                refUrl="",
                stationMapId=line.extra_info["stationMapId"],
                planId=line.extra_info["id"],
                planDate=line.drv_date,
                receUserName=order.contact_info["name"],
                receUserCardCode=order.contact_info["id_number"],
                receUserContact=rebot.telephone,
                orderCount=1,
                arMoney=order.order_price,
                passengerStr=json.dumps(passenger_info),
                yhqMoney=0,
                yhqId="",
                tickType=ticket_type,
                endTypeId=d_end_type,
                endId=end_city_id,
                startCityId=sta_city_id,
                submitId=token,
                redPayMoney="0.00",
                reduceActionId="",
                reduceMoney=0,
                code="",
                capture="",
                schSource=0
            )
            ret = self.send_lock_request(order, rebot, submit_data)
            flag = int(ret["flag"])
            if flag == 1:
                expire_time = dte.now()+datetime.timedelta(seconds=10*60)
                lock_result.update({
                    "result_code": 1,
                    "result_reason": "",
                    "pay_url": "",
                    "raw_order_no": "",
                    "expire_datetime": expire_time,
                    "source_account": rebot.telephone,
                    "lock_info": ret,
                })
            else:
                lock_result.update({
                    "result_code": 0,
                    "result_reason": str(ret),
                    "pay_url": "",
                    "raw_order_no": "",
                    "expire_datetime": None,
                    "source_account": rebot.telephone,
                    "lock_info": ret,
                })
            return lock_result

    def send_lock_request(self, order, rebot, data):
        """
        单纯向源站发请求
        """
        submit_url = "http://m.changtu.com/order/submitOrder.htm"
        headers = {
            "User-Agent": rebot.user_agent,
            "Content-Type": "application/x-www-form-urlencoded",
        }
        cookies = json.loads(rebot.cookies)
        resp = requests.post(submit_url,
                             data=urllib.urlencode(data),
                             headers=headers,
                             cookies=cookies,)
        ret = resp.json()
        return ret

    def send_lock_request_web(self, order, rebot, data):
        """
        单纯向源站发请求
        """
        submit_url = "http://m.changtu.com/order/submitOrder.htm"
        headers = {
            "User-Agent": rebot.user_agent,
            "Content-Type": "application/x-www-form-urlencoded",
        }
        cookies = json.loads(rebot.cookies)
        resp = requests.post(submit_url,
                             data=urllib.urlencode(data),
                             headers=headers,
                             cookies=cookies,)
        ret = resp.json()
        return ret

    def send_order_request(self, rebot, order):
        detail_url = "http://m.changtu.com/user/order/orderDetail.htm?orderId=%s" % order.lock_info["orderId"]
        headers = {
            "User-Agent": rebot.user_agent,
        }
        cookies = json.loads(rebot.cookies)
        r = requests.get(detail_url, headers=headers, cookies=cookies)
        soup = BeautifulSoup(r.content, "lxml")
        order_no = soup.select(".orderTime .font_arial")[0].get_text().strip()
        state = soup.select(".orderTime .right")[0].get_text().strip()
        return {
            "order_no": order_no,
            "state": state,
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
        rebot = ChangtuWebRebot.objects.get(telephone=order.source_account)
        ret = self.send_order_request(rebot, order=order)
        raw_order = ret["order_no"]
        if raw_order and raw_order != order.raw_order_no:
            order.modify(raw_order_no=raw_order)
        state = ret["state"]
        if state == "订单关闭":
            result_info.update({
                "result_code": 2,
                "result_msg": state,
            })
        elif state == "待出票":
            result_info.update({
                "result_code": 4,
                "result_msg": state,
            })
        elif state=="购票成功":
            result_info.update({
                "result_code": 1,
                "result_msg": state,
                "pick_code_list": [],
                "pick_msg_list": [],
            })
        return result_info

    def get_pay_page(self, order, valid_code="", session=None, pay_channel="alipay" ,**kwargs):
        rebot = ChangtuWebRebot.objects.get(telephone=order.source_account)

        is_login = rebot.test_login_status()
        if not is_login and valid_code:
            info = json.loads(session["pay_login_info"])
            headers = info["headers"]
            cookies = info["cookies"]
            params = {
                "username": rebot.telephone,
                "password": rebot.password,
                "captcha": valid_code,
                "comCheckboxFlag": "true",
            }
            custom_headers = {}
            custom_headers.update(headers)
            custom_headers.update({"Content-Type": "application/x-www-form-urlencoded"})
            r = requests.post("https://passport.changtu.com/login/ttslogin.htm",
                              data=urllib.urlencode(params),
                              headers=custom_headers,
                              allow_redirects=False,
                              cookies=cookies)
            cookies.update(dict(r.cookies))
            rebot.modify(cookies=json.dumps(cookies))
        if not is_login:
            is_login = rebot.test_login_status()

        if is_login:
            if order.status == STATUS_LOCK_RETRY:
                fail_code = order.lock_info.get("failReason", "")
                if valid_code:
                    self.lock_ticket(order, valid_code=valid_code)
                elif fail_code == "13":
                    data = {
                        "cookies": json.loads(rebot.cookies),
                        "headers": {"User-Agent": random.choice(BROWSER_USER_AGENT)},
                        "valid_url": "http://www.changtu.com/dverifyCode/order?t=%s" % time.time(),
                    }
                    session["pay_login_info"] = json.dumps(data)
                    return {"flag": "input_code", "content": ""}
            if order.status == STATUS_WAITING_ISSUE:
                pay_url = "http://www.changtu.com/pay/submitOnlinePay.htm"
                headers = {
                    "User-Agent": rebot.user_agent,
                    "Content-Type": "application/x-www-form-urlencoded",
                }
                params = {
                    "balance":"0.00",
                    "payModel":33,
                    "payPwd":"",
                    "balanceFlag":"N",
                    "orderId":order.lock_info["orderId"]
                }
                cookies = json.loads(rebot.cookies)
                r = requests.post(pay_url, data=urllib.urlencode(params), headers=headers, cookies=cookies)
                return {"flag": "html", "content": r.content}
        else:
            data = {
                "cookies": {},
                "headers": {"User-Agent": random.choice(BROWSER_USER_AGENT)},
                "valid_url": "https://passport.changtu.com/dverifyCode/login?ts=%s" % time.time()
            }
            session["pay_login_info"] = json.dumps(data)
            return {"flag": "input_code", "content": ""}

    def do_refresh_line(self, line):
        result_info = {
            "result_msg": "",
            "update_attrs": {},
        }
        detail_url = "http://www.changtu.com/chepiao/queryOneSch.htm"
        params = dict(
            id=line.extra_info["id"],
            stationMapId=line.extra_info["stationMapId"],
            getModel=line.extra_info["getModel"],
            ticketType=line.extra_info["ticketTypeStr"].split(",")[0],
            schSource=0
        )
        headers={"User-Agent": random.choice(BROWSER_USER_AGENT)}
        r = requests.get("%s?%s" % (detail_url, urllib.urlencode(params)), headers=headers)
        res = r.json()
        if res["flag"] != "true":
            result_info.update(result_msg="flag is false", update_attrs={"left_tickets": 0})
            return result_info
        result_msg = "ok"
        full_price = res["ticketMoney"]
        left_tickets = res["seatAmount"]

        confim_url = "http://www.changtu.com/chepiao/confirmSch.htm"
        sta_city_id, s_pinyin = line.s_city_id.split("|")
        params = dict(
            id=line.extra_info["id"],
            stationMapId=line.extra_info["stationMapId"],
            schSource=0,
            drvDate=line.drv_date,
            cityId=sta_city_id,
        )
        r = requests.get("%s?%s" % (confim_url, urllib.urlencode(params)), headers=headers)
        res = r.json()
        if res["flag"] != "true":
            result_msg = res["msg"]

        result_info.update(result_msg=result_msg,
                           update_attrs={
                               "full_price": full_price,
                               "left_tickets": left_tickets,
                           })
        return result_info
