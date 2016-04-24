#!/usr/bin/env python
# encoding: utf-8
import random
import requests
import json
import urllib
import datetime
import time
import re
import traceback

from app.constants import *
from app import line_log
from app.flow.base import Flow as BaseFlow
from app.models import ChangtuWebRebot
from datetime import datetime as dte
from bs4 import BeautifulSoup


class Flow(BaseFlow):

    name = "changtu"

    def do_lock_ticket(self, order, valid_code="", login_checked=False):
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
            # 未登录
            if not login_checked and not rebot.test_login_status():
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
            r = rebot.http_get("%s?%s" %(form_url,urllib.urlencode(params)),
                             headers={"User-Agent": rebot.user_agent},
                             cookies=cookies)
            soup = BeautifulSoup(r.content, "lxml")
            try:
                token = soup.select("#token")[0].get("value")
            except:
                rebot.modify(ip="")
                return
            passenger_info = {}
            for i, r in enumerate(order.riders):
                passenger_info.update({
                    "ticketInfo_%s" % i: "1♂%s♂%s♂0♂♂N" % (r["name"], r["id_number"])
                })

            ticket_info = {
                "refUrl": "http://www.changtu.com/",
                "stationMapId": line.extra_info["stationMapId"],
                "planId": line.extra_info["id"],
                "planDate": line.drv_date,
                "orderCount": order.ticket_amount,
                "arMoney": order.order_price,
                "passengerStr": passenger_info,
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
            }

            submit_data = {
                "saveReceUserFlag": "N",
                "receUserName": order.contact_info["name"],
                "receUserCardCode": order.contact_info["id_number"],
                "receUserContact": order.contact_info["telephone"],
                "t": token,
                "fraud": json.dumps({"verifyCode": valid_code}),
                "ordersJson": json.dumps([ticket_info], ensure_ascii=False),
                "orderType": -1,
                "reserveNearbyFlag": "N",
            }

            ret = self.send_lock_request(order, rebot, submit_data)
            msg = ret.get("msg", "")
            if not ret:
                lock_result.update({
                    "result_code": 2,
                    "result_reason": "存在待支付单 "+msg,
                    "source_account": rebot.telephone,
                    "lock_info": ret,
                })
                return lock_result

            flag = int(ret["flag"])
            if flag == 1:
                expire_time = dte.now()+datetime.timedelta(seconds=10*60)
                lock_result.update({
                    "result_code": 1,
                    "result_reason": msg,
                    "pay_url": "",
                    "raw_order_no": "",
                    "expire_datetime": expire_time,
                    "source_account": rebot.telephone,
                    "lock_info": ret,
                })
            else:
                code_names = {
                    "1": "联系人姓名格式不正确",
                    "2": "联系人身份证号不正确",
                    "3": "联系人手机号不正确",
                    "4": "乘车人姓名格式不正确",
                    "5": "乘车人身份证号不正确",
                    "6": "您当前不符合立减条件，订单提交失败",
                    "7":  "余票不足，提交订单失败",
                    "000010": "验证码输入错误，请重新输入",
                    "11": "需要验证码",
                    "12": "验证码输入错误",
                    "13": "需要验证码",
                    "14": "需要短信验证码",
                    "000495": "不能重复购买",
                }
                fail_code = ret.get("failReason", "")
                msg = code_names.get(fail_code, "")+" "+msg
                if fail_code in ["13", "11", "12", "000010", "14"]:   # 要输字母验证码
                    lock_result.update({
                        "result_code": 2,
                        "result_reason": "%s-%s" % (fail_code, msg),
                        "source_account": rebot.telephone,
                        "lock_info": ret,
                    })
                elif fail_code in ["000124", "000240"]:
                    lock_result.update({
                        "result_code": 0,
                        "result_reason": "%s-%s" % (fail_code, msg),
                        "source_account": rebot.telephone,
                        "lock_info": ret,
                    })
                else:   # 未知错误
                    if "无效订单" in msg:
                        rebot.modify(cookies="{}", ip="")
                    lock_result.update({
                        "result_code": 2,
                        "result_reason": "%s-%s" % (fail_code, msg),
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
        submit_url = "http://www.changtu.com/trade/order/submitOrders.htm"
        headers = {
            "User-Agent": rebot.user_agent,
            "Content-Type": "application/x-www-form-urlencoded; charset=UTF-8",
        }
        cookies = json.loads(rebot.cookies)
        resp = rebot.http_post(submit_url,
                             data=urllib.urlencode(data),
                             headers=headers,
                             cookies=cookies,)
        s = resp.content
        return json.loads(s[s.index("(")+1: s.rindex(")")])

    def send_order_request(self, order, rebot=None):
        if not rebot:
            rebot = order.get_lock_rebot()
        detail_url = "http://www.changtu.com/user/orderDetail.htm?orderId=%s&_=%s" % (order.lock_info["orderIds"][0]["orderId"], time.time())
        headers = {
            "User-Agent": rebot.user_agent,
        }
        cookies = json.loads(rebot.cookies)
        r = rebot.http_get(detail_url, headers=headers, cookies=cookies)
        order_no = re.findall(r"订单号：(\d+)", r.content)[0]
        state = re.findall(r"订单状态：(\S+)<", r.content)[0]
        pick_no_lst = re.findall(r"取票号：(\d+)", r.content)
        pick_no = pick_no_lst and pick_no_lst[0] or ""
        pick_code_lst  = re.findall(r"取票密码：(\d+)", r.content)
        pick_code = pick_code_lst and pick_code_lst[0] or ""
        return {
            "order_no": order_no,
            "state": state,
            "pick_no": pick_no,
            "pick_code": pick_code,
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
        ret = self.send_order_request(order, rebot=rebot)
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
        elif state in ["已退款", "退款处理中"]:
            result_info.update({
                "result_code": 3,
                "result_msg": state,
            })
        elif state=="订单成功":
            pick_no, pick_code = ret["pick_no"], ret["pick_code"]
            msg_list = []
            code_list = []
            dx_info = {
                "time": order.drv_datetime.strftime("%Y-%m-%d %H:%M"),
                "start": order.line.s_sta_name,
                "end": order.line.d_sta_name,
                "code": pick_code,
                "no": pick_no,
                "raw_order": order.raw_order_no,
                "order": order.raw_order_no,
                "amount": order.ticket_amount,
            }
            province = getattr(order.line, "s_province", None)
            if pick_code and pick_no:
                dx_tmpl = DUAN_XIN_TEMPL["changtu2"]
                code_list.append(pick_code)
                msg_list.append(dx_tmpl % dx_info)
            elif province and province == "山东":
                dx_tmpl = DUAN_XIN_TEMPL["changtu_sd"]
                code_list.append("")
                msg_list.append(dx_tmpl % dx_info)
            else:
                dx_tmpl = DUAN_XIN_TEMPL["changtu1"]
                code_list.append("")
                msg_list.append(dx_tmpl % dx_info)
            result_info.update({
                "result_code": 1,
                "result_msg": state,
                "pick_code_list": code_list,
                "pick_msg_list": msg_list,
            })
        return result_info

    def get_pay_page(self, order, valid_code="", session=None, pay_channel="alipay" ,**kwargs):
        rebot = order.get_lock_rebot()

        is_login = rebot.test_login_status()
        if not is_login and valid_code:
            key = "pay_login_info_%s_%s" % (order.order_no, order.source_account)
            info = json.loads(session[key])
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
            r = rebot.http_post("https://passport.changtu.com/login/ttslogin.htm",
                              data=urllib.urlencode(params),
                              headers=custom_headers,
                              allow_redirects=False,
                              cookies=cookies)
            cookies.update(dict(r.cookies))
            rebot.modify(cookies=json.dumps(cookies))

        is_login = is_login or rebot.test_login_status()
        if is_login:
            if order.status == STATUS_LOCK_RETRY:
                self.lock_ticket(order, valid_code=valid_code, login_checked=True)
                order.reload()
                fail_code = order.lock_info.get("failReason", "")
                if fail_code in ["13", "11", "12", "000010", "14"]:
                    data = {
                        "cookies": json.loads(rebot.cookies),
                        "headers": {"User-Agent": rebot.user_agent},
                        "valid_url": "http://www.changtu.com/dverifyCode/order?t=%s" % time.time(),
                    }
                    key = "pay_login_info_%s_%s" % (order.order_no, order.source_account)
                    session[key] = json.dumps(data)
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
                    "orderId":order.lock_info["orderIds"][0]["orderId"]
                }
                cookies = json.loads(rebot.cookies)
                r = rebot.http_post(pay_url, data=urllib.urlencode(params), headers=headers, cookies=cookies)
                soup = BeautifulSoup(r.content, "lxml")
                raw_form = {}
                for obj in soup.find_all("input"):
                    name, val = obj.get("name"), obj.get("value")
                    if name in ["None", "none", '']:
                        continue
                    raw_form[name] = val
                pay_url = "http://nps.trip8080.com/pay.action"
                r = rebot.http_post(pay_url, data=urllib.urlencode(raw_form), headers=headers, cookies=cookies)
                data = self.extract_alipay(r.content)
                pay_money = float(data["total_fee"])
                trade_no = data["out_trade_no"]
                if order.pay_money != pay_money or order.pay_order_no != trade_no:
                    order.modify(pay_money=pay_money, pay_order_no=trade_no)
                return {"flag": "html", "content": r.content}
        else:
            data = {
                "cookies": {},
                "headers": {"User-Agent": random.choice(BROWSER_USER_AGENT)},
                "valid_url": "https://passport.changtu.com/dverifyCode/login?ts=%s" % time.time()
            }
            key = "pay_login_info_%s_%s" % (order.order_no, order.source_account)
            session[key] = json.dumps(data)
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
        rebot = ChangtuWebRebot.get_one()
        try:
            r = rebot.http_get("%s?%s" % (detail_url, urllib.urlencode(params)), headers=headers)
        except:
            result_info.update(result_msg="exception_ok", update_attrs={"left_tickets": 2, "refresh_datetime": dte.now()})
            line_log.info("%s\n%s", "".join(traceback.format_exc()), locals())
            return result_info
        res = r.json()
        if res["flag"] != "true":
            result_info.update(result_msg="flag is false", update_attrs={"left_tickets": 0})
            return result_info
        result_msg = "ok"
        full_price = float(res["ticketMoney"])
        left_tickets = int(res["seatAmount"])

        confim_url = "http://www.changtu.com/chepiao/confirmSch.htm"
        sta_city_id, s_pinyin = line.s_city_id.split("|")
        params = dict(
            id=line.extra_info["id"],
            stationMapId=line.extra_info["stationMapId"],
            schSource=0,
            drvDate=line.drv_date,
            cityId=sta_city_id,
        )
        r = rebot.http_get("%s?%s" % (confim_url, urllib.urlencode(params)), headers=headers)
        res = r.json()
        if res["flag"] != "true":
            result_msg = res["msg"]

        result_info.update(result_msg=result_msg,
                           update_attrs={
                               "full_price": full_price,
                               "left_tickets": left_tickets,
                           })
        return result_info
