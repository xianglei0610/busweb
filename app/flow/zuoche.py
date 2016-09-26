#!/usr/bin/env python
# encoding: utf-8

import random
import json
import urllib
import datetime
import re

from app.constants import *
from app.flow.base import Flow as BaseFlow
from app.models import ZuocheWapRebot
from datetime import datetime as dte
from bs4 import BeautifulSoup


class Flow(BaseFlow):

    name = "zuoche"

    def do_lock_ticket(self, order):
        line = order.line
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
        rebot = order.get_lock_rebot()

        is_login = rebot.test_login_status()
        if not is_login:
            if rebot.login() == "OK":
                is_login = 1
        # 未登录
        if not is_login:
            lock_result.update({
                "result_code": 2,
                "source_account": rebot.telephone,
                "result_reason": u"账号未登录",
            })
            return lock_result

        cookies = json.loads(rebot.cookies)
        id_info = rebot.add_riders(order)
        if len(id_info) != len(order.riders):
            lock_result.update({
                "result_code": 2,
                "source_account": rebot.telephone,
                "result_reason": u"[系统]添加乘客出错",
            })
            return lock_result

        # 开车时间检查
        if line.extra_info["id"].split(",")[0].split("$")[1] != line.drv_datetime.strftime("%Y%m%d%H%M"):
            lock_result.update({
                "result_code": 2,
                "source_account": rebot.telephone,
                "result_reason": u"[系统]开车时间不一致",
            })
            return lock_result

        headers = {"User-Agent": rebot.user_agent,}
        passengers = []
        the_pick = 0
        for i, r in enumerate(order.riders):
            passengers.append({"name": r["name"], "mobile": r["telephone"], "cardNo": r["id_number"], "id": id_info[i]})
            if r["id_number"] == order.contact_info["id_number"]:
                the_pick = i
        params = {
            "id": line.extra_info["id"],
            "passengers": json.dumps(passengers),
            "takeuser": json.dumps(passengers[the_pick]),
            "vouchar": 0,
            "couponid": "",
        }
        url = "http://xqt.zuoche.com/xqt/sorder.jspx?%s" % urllib.urlencode(params)
        r = rebot.http_get(url, headers=headers, cookies=cookies)
        ret = r.json()

        errmsg = ret["msg"]
        if ret.get("state", "") == "ok":
            expire_time = dte.now()+datetime.timedelta(seconds=2*60)
            lock_result.update({
                "result_code": 1,
                "result_reason": errmsg,
                "raw_order_no": "",
                "expire_datetime": expire_time,
                "source_account": rebot.telephone,
                "lock_info": ret,
            })
        else:
            code = 2
            if "班次已售罄" in errmsg or "座位不足" in errmsg:
                code = 0
                self.close_line(order.line, reason=errmsg)
            lock_result.update({
                "result_code": code,
                "result_reason": errmsg,
                "source_account": rebot.telephone,
            })
        return lock_result


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
        detail = self.send_order_request(order)
        state, pick_code = detail["state"], detail["pick_code"]
        if u"交易完成" in state:
            dx_info = {
                "time": order.drv_datetime.strftime("%Y-%m-%d %H:%M"),
                "start": order.line.s_sta_name,
                "end": order.line.d_sta_name,
                "code": pick_code,
                'raw_order': order.raw_order_no,
            }
            dx_tmpl = DUAN_XIN_TEMPL[SOURCE_ZUOCHE]
            pick_msg = dx_tmpl % dx_info
            result_info.update({
                "result_code": 1,
                "result_msg": state,
                "pick_code_list": [pick_code],
                "pick_msg_list": [pick_msg],
            })
        return result_info

    def send_order_request(self, order):
        rebot = order.get_lock_rebot()
        url = "http://xqt.zuoche.com/xqt/orderdetail.jspx?id=%s" % order.lock_info["id"]
        r = rebot.http_get(url, headers={"User-Agent": rebot.user_agent}, cookies=json.loads(rebot.cookies))

        soup = BeautifulSoup(r.content, "lxml")
        try:
            raw_order = re.findall(ur"\(订单号 (\S+)\)", unicode(soup.select_one(".title").text))[0]
            state = soup.select_one(".order_other_info").find("div").text
            pick_code = ""
            pay_money = float(unicode(soup.select_one(".amount .pay").text).strip().lstrip(u"支付金额：").strip().rstrip(u"元").replace(",", ""))
            if order.raw_order_no != raw_order:
                order.modify(raw_order_no=raw_order, pay_money=pay_money)
            if "交易完成" in state:
                pick_code = re.findall(ur"取票密码：(\d+)", soup.select_one(".password").text)[0]
        except Exception, e:
            print e
            state, raw_order, pick_code = "", "", ""
        return {"state": state, "raw_order": raw_order, "pick_code": pick_code}

    def get_pay_page(self, order, valid_code="", session=None, pay_channel="alipay" ,**kwargs):
        rebot = order.get_lock_rebot()
        is_login = rebot.test_login_status()
        if not is_login:
            is_login = (rebot.login() == "OK")

        if is_login:
            if order.status in [STATUS_LOCK_RETRY, STATUS_WAITING_LOCK]:
                self.lock_ticket(order)
            if order.status == STATUS_WAITING_ISSUE:
                self.do_refresh_issue(order)
                url = "http://xqt.zuoche.com/xqt/pay.jspx?id=%s" % order.lock_info["id"]
                headers = {"User-Agent": rebot.user_agent}
                cookies = json.loads(rebot.cookies)
                try:
                    r = rebot.http_get(url, headers=headers, cookies=cookies)
                    soup = BeautifulSoup(r.content, "lxml")
                    pay_url = soup.find("img", attrs={"alt":"支付宝"}).parent.get("href")
                    r = rebot.http_get(pay_url, headers=headers, cookies=cookies)
                    return {"flag": "html", "content": r.content}
                except:
                    return {"flag": "error", "content": r.content}
        else:
            return {"flag": "error", "content": u"账号登录失败"}

    def do_refresh_line(self, line):
        result_info = {"result_msg": "","update_attrs": {},}
        now = dte.now()
        url = "http://xqt.zuoche.com/xqt/updateprice.jspx?id=%s" % line.extra_info["id"]

        headers={"User-Agent": random.choice(MOBILE_USER_AGENG)}
        rebot = ZuocheWapRebot.get_one()
        try:
            r = rebot.http_get(url, headers=headers)
            res = r.json()
            if res["isCanBuy"]:
                cookies = json.loads(rebot.cookies)
                r = rebot.http_get("http://xqt.zuoche.com/xqt/forder.jspx?id=%s" % line.extra_info["id"], headers=headers, cookies=cookies)
                left_tickets = int(re.findall(r"余票：(\d+)", r.content)[0])
                result_info.update(result_msg="ok", update_attrs={"left_tickets": left_tickets, "refresh_datetime": now})
            else:
                result_info.update(result_msg="error_default", update_attrs={"left_tickets": 0, "refresh_datetime": now})
        except Exception, e:
            result_info.update(result_msg="error_default", update_attrs={"left_tickets": 4, "refresh_datetime": now})

        return result_info
