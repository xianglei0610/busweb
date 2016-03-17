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
                elif u"同一IP一天最多可订、购20张" in res["msg"]:
                    cqky_proxy.clear_current_proxy()
                    lock_result.update({
                        "result_code": 2,
                        "source_account": rebot.telephone,
                        "result_reason": res["msg"],
                    })
                else:
                    lock_result.update({
                        "result_code": 2,
                        "source_account": rebot.telephone,
                        "result_reason": res["msg"],
                    })
            elif "您未登录或登录已过期" in res["msg"]:
                lock_result.update({
                     "result_code": 2,
                     "source_account": rebot.telephone,
                     "result_reason": u"账号未登录",
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
            r = self.get(base_url, headers=headers)
            soup = BeautifulSoup(r.content, "lxml")
            headers.update({"Content-Type": "application/x-www-form-urlencoded; charset=UTF-8"})
            params ={
                "__VIEWSTATE": soup.select("#__VIEWSTATE")[0].get("value"),
                "__EVENTVALIDATION": soup.select("#__EVENTVALIDATION")[0].get("value"),
                "ctl00$FartherMain$NavigationControl1$CustRBList": "",
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
        else:
            base_url = "http://www.96096kp.com/OrderConfirm.aspx"
            r = self.get(base_url, headers=headers)
            soup = BeautifulSoup(r.content, "lxml")
            headers.update({"Content-Type": "application/x-www-form-urlencoded; charset=UTF-8"})
            params ={
                "__VIEWSTATE": soup.select("#__VIEWSTATE")[0].get("value"),
                "__EVENTVALIDATION": soup.select("#__EVENTVALIDATION")[0].get("value"),
                "ctl00$FartherMain$radioListPayType": "OnlineAliPay,支付宝在线支付",
                "ctl00$FartherMain$hideIsSubmit": "true",
            }
        r = self.post(base_url,
                      data=urllib.urlencode(params),
                      headers=headers,
                      cookies=cookies,)
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
        r = self.post(base_url,
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
        r = self.post(base_url,
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
        r = self.post(base_url,
                          data=urllib.urlencode(params),
                          headers=headers,
                          cookies=cookies,)
        res = json.loads(trans_js_str(r.content))
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
        r = self.post(base_url, data=urllib.urlencode(params), headers=headers, cookies=cookies)
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
        elif not ret:
            result_info.update({
                "result_code": 2,
                "result_msg": "在源站没找到订单信息",
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
        cookies = json.loads(rebot.cookies)
        r = self.post(base_url, data=urllib.urlencode(params), headers=headers, cookies=cookies)
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
                r = self.post(login_url, data=urllib.urlencode(params), headers=headers, cookies=cookies)
                cookies.update(dict(r.cookies))
                rebot.modify(cookies=json.dumps(cookies))
            self.lock_ticket(order)

        if order.status == STATUS_WAITING_ISSUE:
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
                "txtBDate": "2016-02-10",
                "txtEDate": "2016-03-10",
                "ctl00$FartherMain$Hidden1": "",
                "txtCusName": "",
                "txtCusPhone": "",
                "ctl00$FartherMain$Hidden2": "",
                "pageNum": ""
            }
            r = requests.post(base_url,
                              data=urllib.urlencode(params),
                              headers=headers)
            return {"flag": "html", "content": r.content}

        if order.status == STATUS_LOCK_RETRY:
            cookies = json.loads(rebot.cookies)
            login_form = "http://www.96096kp.com/CusLogin.aspx"
            valid_url = "http://www.96096kp.com/ValidateCode.aspx"
            headers = {"User-Agent": random.choice(BROWSER_USER_AGENT)}
            r = self.get(login_form, headers=headers, cookies=cookies)
            cookies.update(dict(r.cookies))
            data = {
                "cookies": cookies,
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
                "bus_num": d["SchLocalCode"],
                "crawl_source": line.crawl_source,
                "drv_datetime": drv_datetime,
            }
            line_id = md5("%(s_city_name)s-%(d_city_name)s-%(drv_datetime)s-%(bus_num)s-%(crawl_source)s" % line_id_args)
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
