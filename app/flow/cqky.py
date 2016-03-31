#!/usr/bin/env python
# encoding: utf-8
import re
import random
import requests
import json
import urllib
import datetime

from app.constants import *
from app.flow.base import Flow as BaseFlow
from app.models import Line, CqkyWebRebot
from datetime import datetime as dte
from app.utils import md5, trans_js_str
from bs4 import BeautifulSoup
from app import order_log
from app.proxy import cqky_proxy
from app.models import Order


class Flow(BaseFlow):

    name = "cqky"

    def get(self, url, **kwargs):
        r = requests.get(url,
                         proxies={"http": "http://%s" % cqky_proxy.current_proxy},
                         timeout=10,
                         **kwargs)
        return r

    def post(self, url, **kwargs):
        r = requests.post(url,
                          proxies={"http": "http://%s" % cqky_proxy.current_proxy},
                          timeout=10,
                          **kwargs)
        return r

    def do_lock_ticket(self, order):
        lock_result = {
            "lock_info": {},
            "source_account": order.source_account,
            "result_code": -1,
            "result_reason": "blank",
            "pay_url": "",
            "raw_order_no": "",
            "expire_datetime": "",
            "pay_money": 0,
        }
        with CqkyWebRebot.get_and_lock(order) as rebot:
            line = order.line

            res = self.request_station_status(line, rebot)
            if res["success"]:
                mode = 2
            else:
                mode = 1

            # 查看购物车列表
            res = self.request_get_shoptcart(rebot)
            # 清空购物车列表
            for ids in res["data"][u"ShopTable"].keys():
                self.request_del_shoptcart(rebot, ids)
            # 加入购物车
            res = self.request_add_shopcart(order, rebot, sta_mode=mode)
            ilst = re.findall(r"(\d) 张车票", res.get("msg", ""))
            if ilst:
                amount = int(ilst[0])
                if amount != order.ticket_amount:
                    order_log.info("[locking] order: %s, 锁票数量不对 %s,%s" % (order.ticket_amount, amount))
                    # 查看购物车列表
                    res = self.request_get_shoptcart(rebot)
                    # 清空购物车列表
                    for ids in res["data"][u"ShopTable"].keys():
                        self.request_del_shoptcart(rebot, ids)
                    lock_result.update({
                        "result_code": 2,
                        "result_reason": u"锁票数量不对",
                    })
                    return lock_result

            if res["success"]:
                res = self.request_lock(order, rebot, sta_mode=mode)
                if res["success"]:
                    expire_time = dte.now()+datetime.timedelta(seconds=15*60)
                    lock_result.update({
                        "result_code": 1,
                        "result_reason": "",
                        "pay_url": "",
                        "raw_order_no": res["raw_order_no"],
                        "expire_datetime": expire_time,
                        "source_account": rebot.telephone,
                        "pay_money": res["pay_money"]
                    })
                elif u"同一IP一天最多可订、购20张" in res["msg"] or u"当前系统维护中" in res["msg"]:
                    rebot.modify(ip="")
                    lock_result.update({
                        "result_code": 2,
                        "source_account": rebot.telephone,
                        "result_reason": res["msg"],
                    })
                elif u"当前用户今天交易数已满" in res["msg"] or u"当前登录用户已被列为可疑用户" in res["msg"]:
                    rebot.remove_doing_order(order)
                    order.modify(source_account="")
                    with CqkyWebRebot.get_and_lock(order) as newrebot:
                        account = newrebot.telephone
                    lock_result.update({
                        "result_code": 2,
                        "source_account": account,
                        "result_reason": res["msg"],
                    })
                elif u"拒绝售票" in res["msg"] or "提前时间不足" in res["msg"] or u"班次席位可售数不足" in res["msg"] or "班次站点无可售席位" in res["msg"]:
                    self.close_line(line, reason=res["msg"])
                    lock_result.update({
                        "result_code": 0,
                        "source_account": rebot.telephone,
                        "result_reason": res["msg"],
                    })
                elif u"可售票数量不足" in res["msg"] or "锁票超时超过10次" in res["msg"] or "当前班次座位资源紧张" in res["msg"] or "可能车站已调整票价" in res["msg"]:
                    self.close_line(line, reason=res["msg"])
                    lock_result.update({
                        "result_code": 0,
                        "source_account": rebot.telephone,
                        "result_reason": res["msg"],
                    })
                elif u"锁位失败" in res["msg"]:
                    lock_result.update({
                        "result_code": 0,
                        "result_reason": res["msg"],
                    })
                else:
                    lock_result.update({
                        "result_code": 2,
                        "source_account": rebot.telephone,
                        "result_reason": res["msg"],
                    })
            elif "您未登录或登录已过期" in res["msg"]:
                rebot.modify(ip="")
                lock_result.update({
                     "result_code": 2,
                     "source_account": rebot.telephone,
                     "result_reason": u"账号未登录",
                 })
            elif u"单笔订单一次只允许购买3张车票" in res["msg"]:
                lock_result.update({
                     "result_code": 2,
                     "result_reason": res["msg"],
                 })
            else:
                lock_result.update({
                    "result_code": 0,
                    "result_reason": "add_shopcart fail, %s" % res["msg"],
                    "source_account": rebot.telephone,
                })
            return lock_result

    def request_lock(self, order, rebot, sta_mode=1):
        headers = {
            "User-Agent": rebot.user_agent,
            "Referer": "http://www.96096kp.com/TicketMain.aspx",
            "Origin": "http://www.96096kp.com",
        }
        cookies = json.loads(rebot.cookies)
        if sta_mode == 1:
            base_url = "http://www.96096kp.com/CommitGoods.aspx"
            r = rebot.http_get(base_url, headers=headers, cookies=cookies)
            soup = BeautifulSoup(r.content, "lxml")
            headers.update({"Content-Type": "application/x-www-form-urlencoded; charset=UTF-8"})
            params ={
                "__VIEWSTATE": soup.select("#__VIEWSTATE")[0].get("value"),
                "__EVENTVALIDATION": soup.select("#__EVENTVALIDATION")[0].get("value"),
                "ctl00$FartherMain$NavigationControl1$CustRBList": "",
                "ctl00$FartherMain$NavigationControl1$o_CustomerName": order.contact_info["name"],
                "ctl00$FartherMain$NavigationControl1$o_Mobele": order.contact_info["telephone"],
                "ctl00$FartherMain$NavigationControl1$o_IdType": 1,
                "ctl00$FartherMain$NavigationControl1$o_IdCard": order.contact_info["id_number"],
                "ctl00$FartherMain$NavigationControl1$o_IdCardConfirm": order.contact_info["id_number"],
                "ctl00$FartherMain$NavigationControl1$radioListPayType": "OnlineAliPay,支付宝在线支付",
                "ctl00$FartherMain$NavigationControl1$o_Email": "kuo86106@qq.com",
                "ctl00$FartherMain$NavigationControl1$ContactAddress": "",
                "ctl00$FartherMain$NavigationControl1$o_Memo": "",
                "ctl00$FartherMain$NavigationControl1$hideIsSubmit": "true",
            }
        else:
            base_url = "http://www.96096kp.com/OrderConfirm.aspx"
            r = rebot.http_get(base_url, headers=headers, cookies=cookies)
            soup = BeautifulSoup(r.content, "lxml")
            headers.update({"Content-Type": "application/x-www-form-urlencoded; charset=UTF-8"})
            params ={
                "__VIEWSTATE": soup.select("#__VIEWSTATE")[0].get("value"),
                "__EVENTVALIDATION": soup.select("#__EVENTVALIDATION")[0].get("value"),
                "ctl00$FartherMain$radioListPayType": "OnlineAliPay,支付宝在线支付",
                "ctl00$FartherMain$hideIsSubmit": "true",
            }
        try:
            r = rebot.http_post(base_url,
                        data=urllib.urlencode(params),
                        headers=headers,
                        cookies=cookies,)
        except requests.exceptions.Timeout, e:
            rebot.modify(ip="")
            lock_info = order.lock_info
            if "lock_timeout_cnt" not in lock_info:
                lock_info["lock_timeout_cnt"] = 0
            lock_info["lock_timeout_cnt"] += 1
            order.modify(lock_info=lock_info)
            if order.lock_info["lock_timeout_cnt"] > 10:
                return {
                    "success": False,
                    "msg": u"锁票超时超过10次",
                }
        soup = BeautifulSoup(r.content, "lxml")
        msg_lst = re.findall(r'<script>alert\("(.+)"\);</script>', r.content)
        msg = ""
        if msg_lst:
            msg = msg_lst[0]
        try:
            order_no = soup.find("input", attrs={"name": "out_trade_no"}).get("value")
            pay_money = float(soup.find("input", attrs={"name": "total_fee"}).get("value"))
            flag = True
        except:
            order_no = ""
            pay_money = ""
            flag = False
        return {
            "success": flag,
            "msg": msg,
            "raw_order_no": order_no,
            "pay_order_no": order_no,
            "pay_money": pay_money,
        }

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
        r = rebot.http_post(base_url,
                      data=urllib.urlencode(params),
                      headers=headers,
                      cookies=cookies)
        return json.loads(trans_js_str(r.content))

    def request_del_shoptcart(self, rebot, sid):
        """
        删除购物车
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
            "cmd": "delCartItem",
            "id": sid,
        }
        r = rebot.http_post(base_url,
                      data=urllib.urlencode(params),
                      headers=headers,
                      cookies=cookies)
        return json.loads(trans_js_str(r.content))

    def request_add_shopcart(self, order, rebot, sta_mode=1):
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
            "classInfo": json.dumps(line.extra_info["raw_info"], ensure_ascii=False),
            "drBusStationCode": line.s_sta_id,
            "drBusStationName": line.s_sta_name,
            "ticketHalfCount": 0,
            "ticketFullCount": order.ticket_amount,
            "ticketChildCount": 0,
            "cmd": "buyTicket",
        }
        if sta_mode == 2:
            lst = []
            for r in order.riders:
                lst.append("1~%s~1~%s~%s~0~false" % (r["name"], r["id_number"], rebot.telephone))
            params.update({
                "passengerMsg": "|".join(lst),
                "contactMsg": "%s~%s~" % (order.contact_info["name"], rebot.telephone),
                "isIns": "false",
            })
        r = rebot.http_post(base_url,
                          data=urllib.urlencode(params),
                          headers=headers,
                          cookies=cookies,)
        try:
            res = json.loads(trans_js_str(r.content))
        except Exception, e:
            rebot.modify(ip="")
            raise e
        order_log.info("[locking] order: %s add shopcart, %s", order.order_no, res.get("msg", ""))
        return res

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
        r = rebot.http_post(base_url, data=urllib.urlencode(params), headers=headers, cookies=cookies)
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
        rebot = CqkyWebRebot.objects.get(telephone=order.source_account)
        ret = self.send_order_request(rebot, order)
        state = ret.get("OrderStatus", "")
        if state == "已支付":
            msg_list = []
            dx_tmpl = DUAN_XIN_TEMPL[SOURCE_CQKY]
            dx_info = {
                "time": order.drv_datetime.strftime("%Y-%m-%d %H:%M"),
                "start": order.line.s_sta_name,
                "end": order.line.d_sta_name,
                "raw_order": order.raw_order_no,
            }
            msg_list.append(dx_tmpl % dx_info)
            result_info.update({
                "result_code": 1,
                "result_msg": state,
                "pick_code_list": [""],
                "pick_msg_list": msg_list,
            })
        return result_info

    def send_order_request(self, rebot, order):
        base_url = "http://www.96096kp.com/UserData/UserCmd.aspx"
        params = {
            "isCheck": "false",
            "ValidateCode": "",
            "IDTypeCode": 1,
            "IDTypeNo": order.contact_info["id_number"],
            "start": 0,
            "limit": 10,
            "Status":  -1,
            "cmd": "OnlineOrderGetList"
        }
        headers = {
            "User-Agent": rebot.user_agent,
            "Referer": "http://www.96096kp.com/TicketMain.aspx",
            "Origin": "http://www.96096kp.com",
            "Content-Type": "application/x-www-form-urlencoded; charset=UTF-8",
        }
        def my_trans_js_str(s):
            """
            {aa:'bb'} ==> {"aa":"bb"}
            """
            for k in set(re.findall("([A-Za-z]+):", s)):
                s= re.sub(r"\b%s\b" % k, '"%s"' % k, s)
            return s
        cookies = json.loads(rebot.cookies)
        r = rebot.http_post(base_url, data=urllib.urlencode(params), headers=headers, cookies=cookies)
        res = json.loads(my_trans_js_str(r.content))
        for d in res["data"]:
            if d["OrderNo"] == order.raw_order_no:
                return d
        params = {
            "isCheck": "false",
            "ValidateCode": "",
            "IDTypeCode": 1,
            "IDTypeNo": order.riders[0]["id_number"],
            "start": 0,
            "limit": 10,
            "Status":  -1,
            "cmd": "OnlineOrderGetList"
        }
        r = rebot.http_post(base_url, data=urllib.urlencode(params), headers=headers, cookies=cookies)
        res = json.loads(trans_js_str(r.content))
        for d in res["data"]:
            if d["OrderNo"] == order.raw_order_no:
                return d
        return {}

    def get_pay_page(self, order, valid_code="", session=None, pay_channel="alipay" ,**kwargs):
        rebot = CqkyWebRebot.objects.get(telephone=order.source_account)
        if order.status == STATUS_LOCK_RETRY:
            if valid_code:
                login_url= "http://www.96096kp.com/UserData/UserCmd.aspx"
                key = "pay_login_info_%s_%s" % (order.order_no, order.source_account)
                info = json.loads(session[key])
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
                try:
                    r = rebot.http_post(login_url, data=urllib.urlencode(params), headers=headers, cookies=cookies)
                    order_log.info("[cqky login] order:%s rebot:%s %s ip:%s", order.order_no, rebot.telephone, r.content, rebot.proxy_ip)
                    if u"用户名或密码错误" in r.content:
                        rebot.remove_doing_order(order)
                        order.modify(source_account="")
                        with CqkyWebRebot.get_and_lock(order) as newrebot:
                            order.update(source_account=newrebot.telephone)
                            rebot = newrebot
                except Exception,e:
                    rebot.modify(ip="")
                    raise e
                cookies.update(dict(r.cookies))
                rebot.modify(cookies=json.dumps(cookies))
            self.lock_ticket(order)

        if order.status == STATUS_WAITING_ISSUE:
            self.check_raw_order_no(order)
            order.reload()
            base_url = "http://www.96096kp.com/GoodsDetail.aspx"
            headers = {
                "User-Agent": rebot.user_agent,
                "Referer": "http://www.96096kp.com/TicketMain.aspx",
                "Origin": "http://www.96096kp.com",
            }
            r = requests.get(base_url, headers=headers)
            soup = BeautifulSoup(r.content, "lxml")
            headers.update({"Content-Type": "application/x-www-form-urlencoded; charset=UTF-8"})
            headers.update({"Referer": "http://www.96096kp.com/GoodsDetail.aspx"})
            params ={
                "__VIEWSTATE": soup.select("#__VIEWSTATE")[0].get("value"),
                "__EVENTVALIDATION": soup.select("#__EVENTVALIDATION")[0].get("value"),
                "ctl00$FartherMain$IDTypeCode": 1,
                "ctl00$FartherMain$IDTypeNo":  order.contact_info["id_number"],
                "ctl00$FartherMain$hiAgainPayOrderNo": order.raw_order_no,
                "txtBDate": "",
                "txtEDate": "",
                "ctl00$FartherMain$Hidden1": "",
                "txtCusName": "",
                "txtCusPhone": "",
                "ctl00$FartherMain$Hidden2": "",
                "pageNum": ""
            }
            r = requests.post(base_url,
                            data=urllib.urlencode(params),
                            headers=headers,)
            return {"flag": "html", "content": r.content}

        if order.status == STATUS_LOCK_RETRY:
            cookies = json.loads(rebot.cookies)
            login_form = "http://www.96096kp.com/CusLogin.aspx"
            valid_url = "http://www.96096kp.com/ValidateCode.aspx"
            headers = {"User-Agent": random.choice(BROWSER_USER_AGENT)}
            r = rebot.http_get(login_form, headers=headers, cookies=cookies)
            cookies.update(dict(r.cookies))
            data = {
                "cookies": cookies,
                "headers": headers,
                "valid_url": valid_url,
            }
            key = "pay_login_info_%s_%s" % (order.order_no, order.source_account)
            session[key] = json.dumps(data)
            return {"flag": "input_code", "content": ""}

    def do_refresh_line(self, line):
        result_info = {
            "result_msg": "",
            "update_attrs": {},
        }
        line_url = "http://www.96096kp.com/UserData/MQCenterSale.aspx"
        params = {
            "StartStation": line.s_city_name,
            "WaitStationCode": "",
            "OpStation": -1,
            "OpAddress": -1,
            "SchDate": line.drv_date,
            "DstNode": line.d_city_name,
            "SeatType": "",
            "SchTime": "",
            "OperMode": "",
            "SchCode": "",
            "txtImgCode": "",
            "cmd": "MQCenterGetClass",
            "isCheck": "false",
        }
        headers = {
            "User-Agent": random.choice(BROWSER_USER_AGENT),
            "Referer": "http://www.96096kp.com",
            "Origin": "http://www.96096kp.com",
            "Content-Type": "application/x-www-form-urlencoded; charset=UTF-8",
        }
        r = self.post(line_url,
                          data=urllib.urlencode(params),
                          headers=headers)
        content = r.content
        for k in set(re.findall("([A-Za-z]+):", content)):
            content = re.sub(r"\b%s\b" % k, '"%s"' % k, content)
        res = json.loads(content)
        now = dte.now()
        if res["success"] != "true":
            result_info.update(result_msg="error response", update_attrs={"left_tickets": 0, "refresh_datetime": now})
            return result_info

        update_attrs = {}
        for d in res["data"]:
            drv_datetime = dte.strptime("%s %s" % (d["SchDate"], d["SchTime"]), "%Y-%m-%d %H:%M")
            line_id_args = {
                "s_city_name": line.s_city_name,
                "d_city_name": line.d_city_name,
                "s_sta_name": d["SchStationName"],
                "d_sta_name": d["SchDstNodeName"],
                "crawl_source": line.crawl_source,
                "drv_datetime": drv_datetime,
            }
            line_id = md5("%(s_city_name)s-%(d_city_name)s-%(drv_datetime)s-%(s_sta_name)s-%(d_sta_name)s-%(crawl_source)s" % line_id_args)
            try:
                obj = Line.objects.get(line_id=line_id)
            except Line.DoesNotExist:
                continue
            info = {
                "full_price": float(d["SchPrice"]),
                "fee": 0,
                "left_tickets": int(d["SchTicketCount"]),
                "refresh_datetime": now,
                "extra_info": {"raw_info": d},
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

    def check_raw_order_no(self, order):
        """
        有时候源站返回的订单号是错的，这时需要从源站搜出来
        """
        if order.status != STATUS_WAITING_ISSUE:
            return
        try:
            other = Order.objects.get(raw_order_no=order.raw_order_no, status__in=[STATUS_ISSUE_SUCC, STATUS_ISSUE_FAIL])
        except Order.DoesNotExist:
            return
        if other.order_no == order.order_no:
            return
        rebot = order.get_lock_rebot()
        base_url = "http://www.96096kp.com/UserData/UserCmd.aspx"
        params = {
            "isCheck": "false",
            "ValidateCode": "",
            "IDTypeCode": 1,
            "IDTypeNo": order.contact_info["id_number"],
            "start": 0,
            "limit": 10,
            "Status":  -1,
            "cmd": "OnlineOrderGetList"
        }
        headers = {
            "User-Agent": rebot.user_agent,
            "Referer": "http://www.96096kp.com/TicketMain.aspx",
            "Origin": "http://www.96096kp.com",
            "Content-Type": "application/x-www-form-urlencoded; charset=UTF-8",
        }
        cookies = json.loads(rebot.cookies)
        r = rebot.http_post(base_url, data=urllib.urlencode(params), headers=headers, cookies=cookies)
        res = json.loads(trans_js_str(r.content))
        order_list = res["data"]

        if order.contact_info["id_number"] != order.riders[0]["id_number"]:
            params = {
                "isCheck": "false",
                "ValidateCode": "",
                "IDTypeCode": 1,
                "IDTypeNo": order.riders[0]["id_number"],
                "start": 0,
                "limit": 10,
                "Status":  -1,
                "cmd": "OnlineOrderGetList"
            }
            r = rebot.http_post(base_url, data=urllib.urlencode(params), headers=headers, cookies=cookies)
            res = json.loads(trans_js_str(r.content))
            order_list.extend(res["data"])

        for d in order_list:
            if d["OrderStatus"] == "未支付" and float(d["OrderMoney"]) == order.order_price and int(d["TicketCount"]) == order.ticket_amount:
                raw_order = d["OrderNo"]
                try:
                    obj = Order.objects.get(raw_order_no=raw_order, status=STATUS_ISSUE_SUCC)
                    if obj.order_no == order.order_no:
                        return
                except Order.DoesNotExist:
                    old = order.raw_order_no
                    order.modify(raw_order_no=raw_order, pay_money=float(d["OrderMoney"]))
                    order_log.info("order:%s change raw_order_no %s to %s", order.order_no, old, order.raw_order_no)
                    return
