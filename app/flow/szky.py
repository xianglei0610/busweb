#!/usr/bin/env python
# encoding: utf-8
import re
import random
import requests
import json
import urllib
import datetime
import traceback
import urlparse

from app.constants import *
from app.flow.base import Flow as BaseFlow
from app.models import Line, SzkyWebRebot
from datetime import datetime as dte
from app.utils import md5, trans_js_str
from bs4 import BeautifulSoup
from app import order_log, line_log
from app.models import Order
from app.proxy import get_proxy


class Flow(BaseFlow):

    name = "szky"

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
        rebot = order.get_lock_rebot()
        line = order.line
        is_login = rebot.check_login()
        if not is_login:
            for i in range(3):
                if rebot.login() == "OK":
                    is_login = True
                    break

        if not is_login:
            lock_result.update({
                "result_code": 2,
                "source_account": rebot.telephone,
                "result_reason": "账号未登录",
            })
            return lock_result

        # 加入购物车
        res = self.request_add_shopcart(order, rebot)
        ilst = re.findall(r"(\d+)\s张车票", str(res.get("msg", "")))
        # 清理购物车
        amount = ilst and int(ilst[0]) or 0
        msg = res.get("msg", "")
        if (amount and amount != order.ticket_amount) or u"单笔订单一次只允许购买3张车票" in msg or u"单笔订单只能购买一个车站的票" in msg:
            res = self.request_get_shoptcart(rebot)
            del_success = False
            for ids in res["data"][u"ShopTable"].keys():
                d = self.request_del_shoptcart(rebot, ids)
                if d.get("success", False):
                    del_success = True
            if not del_success:
                rebot.modify(cookies="{}")
                rebot = order.change_lock_rebot()
            lock_result.update({
                "result_code": 2,
                "result_reason": u"购物车数量不对:%s, %s" % (msg, del_success),
                "source_account": rebot.telephone,
            })
            return lock_result

        def _check_fail(msg):
            if u"当前系统维护中" in msg:
                return False
            lst = [
                u"可售票数量不足",
                u"锁票超时超过10次",
                u"当前班次座位资源紧张",
                u"可能车站已调整票价",
                u"拒绝售票",
                u"提前时间不足",
                u"班次席位可售数不足",
                u"班次站点无可售席位",
                u"班次状态为停班",
                u"无可售席位资源",
                u"可售数不足",
                u"班次状态为保班",
                u"无可售席位",
                u"中心转发30003请求TKLock_3失败",
                u"班次状态为作废",
                u"不允许锁位",
                u"锁位失败",
                u"添加订单记录失败"
            ]
            for s in lst:
                if s in msg:
                    return True
            return False

        if res["success"]:
            res = self.request_lock(order, rebot)
            if res["success"]:
                try:
                    other = Order.objects.get(raw_order_no=res["raw_order_no"])
                except Order.DoesNotExist:
                    other = ''
                if other:
                    rebot.modify(cookies="{}")
                    rebot = order.change_lock_rebot()
                    lock_result.update({
                        "result_code": 2,
                        "source_account": rebot.telephone,
                        "result_reason": '系统中存在已经存在订单号:%s' % res["raw_order_no"]
                        })
                    return lock_result
                expire_time = dte.now()+datetime.timedelta(seconds=20*60)
                lock_result.update({
                    "result_code": 1,
                    "result_reason": "",
                    "pay_url": "",
                    "raw_order_no": res["raw_order_no"],
                    "expire_datetime": expire_time,
                    "source_account": rebot.telephone,
                    "pay_money": res["pay_money"],
                    "lock_info": {},
                })
            elif u"同一IP一天最多可订" in res["msg"]:
#                 res["msg"] = "ip: %s %s" % (rebot.proxy_ip, res["msg"])
#                 get_proxy("szky").set_black(rebot.proxy_ip)
                rebot.modify(ip="")
                lock_result.update({
                    "result_code": 2,
                    "source_account": rebot.telephone,
                    "result_reason": res["msg"]
                })
            elif u"当前用户今天交易数已满" in res["msg"] or u"当前登录用户已被列为可疑用户" in res["msg"] or u"当前系统维护中" in res["msg"]:
                rebot.modify(cookies="{}")
                rebot = order.change_lock_rebot()
                lock_result.update({
                    "result_code": 2,
                    "source_account": rebot.telephone,
                    "result_reason":  res["msg"]
                })
            elif u"例行维护" in res["msg"] or u"暂停网上购票业务" in res["msg"]:
                lock_result.update({
                    "result_code": 2,
                    "source_account": rebot.telephone,
                    "result_reason":  res["msg"]
                })
            elif _check_fail(res["msg"]):
                self.close_line(line, reason=res["msg"])
                lock_result.update({
                    "result_code": 0,
                    "source_account": rebot.telephone,
                    "result_reason": res["msg"],
                })
            else:
                lock_result.update({
                    "result_code": 2,
                    "source_account": rebot.telephone,
                    "result_reason":  res["msg"]
                })
        elif u"您未登录或登录已过期" in res["msg"] or u"例行维护" in res["msg"]:
            rebot.modify(ip="")
            lock_result.update({
                 "result_code": 2,
                 "source_account": rebot.telephone,
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
        }
        cookies = json.loads(rebot.cookies)
        base_url = "http://124.172.118.225/User/CommitGoods.aspx"
        r = rebot.http_get(base_url, headers=headers, cookies=cookies)
        content = r.content
        soup = BeautifulSoup(content, "lxml")
        headers.update({
                        "Content-Type": "application/x-www-form-urlencoded; charset=UTF-8",
                        "Referer": "http://124.172.118.225/User/CommitGoods.aspx",
                    })
        params = {
            "__EVENTTARGET": soup.select("#__EVENTTARGET")[0].get("value"),
            "__EVENTARGUMENT": soup.select("#__EVENTARGUMENT")[0].get("value"),
            "__VIEWSTATE": soup.select("#__VIEWSTATE")[0].get("value"),
            "__EVENTVALIDATION": soup.select("#__EVENTVALIDATION")[0].get("value"),
            "__VIEWSTATEGENERATOR": soup.select("#__VIEWSTATEGENERATOR")[0].get("value"),
            "ctl00$FartherMain$o_CustomerName": order.contact_info["name"],
            "ctl00$FartherMain$o_Mobele": order.contact_info["telephone"],
            "ctl00$FartherMain$o_IdType": 1,
            "ctl00$FartherMain$o_IdCard": order.contact_info["id_number"],
            "ctl00$FartherMain$radioListPayType": "OnlineUnionPay,银联在线支付",
            "ctl00$FartherMain$o_Email": '',
            "ctl00$FartherMain$ContactAddress": "",
            "ctl00$FartherMain$o_Memo": "",
            "ctl00$FartherMain$hideIsSubmit": "true",
        }

        r = rebot.http_post(base_url,
                            data=urllib.urlencode(params),
                            headers=headers,
                            cookies=cookies,
                            timeout=90,
                            allow_redirects=False)
        location_url = r.headers.get('location', '')
        cookies.update(dict(r.cookies))
        msg = ""
        order_no = ""
        pay_money = ""
        flag = False
        if location_url and location_url == '/User/SendOI.aspx':
            pay_url = "http://124.172.118.225"+location_url
            r = rebot.http_get(pay_url,
                               headers=headers,
                               cookies=cookies,
                               )
            soup = BeautifulSoup(r.content, "lxml")
            try:
                order_no = soup.find("input", attrs={"name": "orderNumber"}).get("value")
                pay_money = float(soup.find("input", attrs={"name": "orderAmount"}).get("value"))/100
                flag = True
            except:
                order_no = ""
                pay_money = ""
                flag = False
        else:
            soup = BeautifulSoup(r.content, "lxml")
            msg_lst = re.findall(r'<script>alert\("(.+)"\);</script>', r.content)
            if msg_lst:
                msg = msg_lst[0]

        return {
                "success": flag,
                "msg": msg,
                "raw_order_no": order_no,
                "pay_order_no": '',
                "pay_money": pay_money,
            }

    def request_get_shoptcart(self, rebot):
        """
        获取购物车条目
        """
        base_url = "http://124.172.118.225/UserData/ShopCart.aspx"
        headers = {
            "User-Agent": rebot.user_agent,
            "Referer": "http://124.172.118.225/User/CommitGoods.aspx",
            "X-Requested-With": "XMLHttpRequest",
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

        def my_trans_js_str(s):
            for k in set(re.findall("([A-Za-z]+):", s)):
                if k in ('http', 'https', 'com', 'cn'):
                    continue
                s = re.sub(r"\b%s\b" % k, '"%s"' % k, s)
            return s
        content = json.loads(my_trans_js_str(r.content))
        return content

    def request_del_shoptcart(self, rebot, sid):
        """
        删除购物车
        """
        base_url = "http://124.172.118.225/UserData/ShopCart.aspx"
        headers = {
            "User-Agent": rebot.user_agent,
            "Referer": "http://124.172.118.225/User/CommitGoods.aspx",
            "X-Requested-With": "XMLHttpRequest",
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
        base_url = "http://124.172.118.225/UserData/ShopCart.aspx"
        headers = {
            "User-Agent": rebot.user_agent,
            "Referer": "http://124.172.118.225/User/Default.aspx",
            "X-Requested-With": "XMLHttpRequest",
            "Content-Type": "application/x-www-form-urlencoded; charset=UTF-8",
            }
        cookies = json.loads(rebot.cookies)
        params = {
            "classInfo": json.dumps(line.extra_info["raw_info"], ensure_ascii=False),
            "drBusStationCode": line.s_sta_id,
            "drBusStationName": line.s_sta_name,
            "ticketFullCount": order.ticket_amount,
            "ticketType": "1",
            "cmd": "buyTicket",
            "IsAgreeBX": "false"
            }

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
        rebot = SzkyWebRebot.objects.get(telephone=order.source_account)
        ret = self.send_order_request(rebot, order)
        state = ret.get("StatusName", "")
        if state == "已支付":
            msg_list = []
            dx_tmpl = DUAN_XIN_TEMPL[SOURCE_SZKY]
            dx_info = {
                "time": order.drv_datetime.strftime("%Y-%m-%d %H:%M"),
                "start": order.line.s_sta_name,
                "end": order.line.d_sta_name,
                "raw_order": order.raw_order_no,
                "person": "取票人",
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
        base_url = "http://124.172.118.225/UserData/UserCmd.aspx"
        params = {
            "BeginDate": "",
            "EndDate": "",
            "OrderNo": order.raw_order_no,
            "start": 0,
            "limit": 10,
            "Status": -1,
            "cmd": "OnlineOrderGetList",
            "UserGuid": rebot.user_id
        }

        headers = {
            "User-Agent": rebot.user_agent,
            "Referer": "http://124.172.118.225/User/OrderQuery.aspx",
            "X-Requested-With": "XMLHttpRequest",
            "Content-Type": "application/x-www-form-urlencoded; charset=UTF-8",
        }

        def my_trans_js_str(s):
            for k in set(re.findall("([A-Za-z_]+):", s)):
                s = re.sub(r"\b%s\b" % k, '"%s"' % k, s)
            return s
        cookies = json.loads(rebot.cookies)
        r = rebot.http_post(base_url, data=urllib.urlencode(params), headers=headers, cookies=cookies)
        try:
            res = json.loads(trans_js_str(r.content))
        except:
            res = json.loads(my_trans_js_str(r.content))
        for d in res["data"]:
            if d["o_OrderNo"] == order.raw_order_no:
                return d
        return {}

    def get_pay_page(self, order, valid_code="", session=None, pay_channel="alipay" ,**kwargs):
        rebot = order.get_lock_rebot()
        is_login = rebot.check_login()
        if order.status in [STATUS_LOCK_RETRY, STATUS_WAITING_LOCK]:
            if not is_login and valid_code:
                key = "pay_login_info_%s_%s" % (order.order_no, order.source_account)
                info = json.loads(session[key])
                headers = info["headers"]
                cookies = info["cookies"]
                msg = rebot.login(valid_code=valid_code, headers=headers, cookies=cookies)
                if msg == "OK":
                    is_login = True
                    rebot.modify(cookies=json.dumps(cookies))
                elif msg == "invalid_pwd":
                    rebot.modify(is_active=False)
                    rebot = order.change_lock_rebot()
            if is_login:
                self.lock_ticket(order)
        order.reload()
        rebot = order.get_lock_rebot()

        if order.status == STATUS_WAITING_ISSUE:
            orderInfo = self.send_order_request(rebot, order)
            if orderInfo:
                if orderInfo['IsAgainPay'] != 1:
                    return {"flag": "error", "content": "订单已支付成功或者失效"}
            else:
                return {"flag": "error", "content": "没拿到源站订单号，不允许支付"}
            base_url = "http://124.172.118.225/User/OrderQuery.aspx"
            headers = {
                "User-Agent": rebot.user_agent,
            }
            cookies = json.loads(rebot.cookies)
            r = rebot.http_get(base_url, headers=headers)
            soup = BeautifulSoup(r.content, "lxml")
            headers.update({"Content-Type": "application/x-www-form-urlencoded; charset=UTF-8",
                            "Referer": "http://124.172.118.225/User/OrderQuery.aspx"})
            params = {
                "__EVENTARGUMENT": soup.select("#__EVENTARGUMENT")[0].get("value"),
                "__EVENTTARGET": soup.select("#__EVENTTARGET")[0].get("value"),
                "__EVENTVALIDATION": soup.select("#__EVENTVALIDATION")[0].get("value"),
                "__VIEWSTATE": soup.select("#__VIEWSTATE")[0].get("value"),
                "__VIEWSTATEGENERATOR": soup.select("#__VIEWSTATEGENERATOR")[0].get("value"),
                "ctl00$FartherMain$hiAgainPayOrderNo": order.raw_order_no,
                "txtBeginDate": '',
                "txtEndDate": ''
            }
            r = rebot.http_post(base_url,
                                data=urllib.urlencode(params),
                                headers=headers,
                                cookies=cookies,
                                timeout=90,
                                allow_redirects=False)
            location_url = r.headers.get('location', '')
            cookies.update(dict(r.cookies))
            if location_url and location_url == '/User/SendOI.aspx':
                pay_url = "http://124.172.118.225"+location_url
                r = rebot.http_get(pay_url,
                                   headers=headers,
                                   cookies=cookies,
                                   )
                order.update(pay_channel='yh')
                return {"flag": "html", "content": r.content}
            else:
                soup = BeautifulSoup(r.content, "lxml")
                msg_lst = re.findall(r"<script>alert\('(.+)'\);</script>", r.content)
#                 <script>alert('该笔订单已不允许再次支付，请重新下单！');window.location.assign('Default.aspx');</script>
                if msg_lst:
                    msg = msg_lst[0]
                    return {"flag": "error", "content": msg}

        if is_login:
            return {"flag": "error", "content": "锁票失败"}

        if order.status in [STATUS_LOCK_RETRY, STATUS_WAITING_LOCK]:
            cookies = {}
            login_form = "http://124.172.118.225/UserData/UserCmd.aspx"
            valid_url = "http://124.172.118.225/ValidateCode.aspx"
            headers = {"User-Agent": rebot.user_agent or random.choice(BROWSER_USER_AGENT)}
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
        rebot = SzkyWebRebot.get_one()
        headers = {"User-Agent": rebot.user_agent}
        for i in range(20):
            try:
                res = rebot.query_code(headers)
            except:
                continue
            if res.get('status', '') == 0:
                cookies = res.get('cookies')
                valid_code = res.get('valid_code')
                break
        result_info = {
            "result_msg": "",
            "update_attrs": {},
        }
        now = dte.now()
        if cookies:
            data = {
                    "DstNode": line.d_sta_name,
                    "OpAddress": "-1",
                    "OpStation":  "-1",
                    "OperMode": '',
                    "SchCode": '',
                    "SchDate": line.drv_date,
                    "SchTime": '',
                    'SeatType': '',
                    'StartStation':  line.s_sta_id,
                    'WaitStationCode': line.extra_info['raw_info']['SchWaitStCode'],
                    'cmd': "MQCenterGetClass",
                    'txtImgCode': valid_code,
                    }
            line_url = 'http://124.172.118.225/UserData/MQCenterSale.aspx'
            headers.update({
                        "Content-Type": "application/x-www-form-urlencoded; charset=UTF-8",
                        "Referer": "http://124.172.118.225/User/Default.aspx",
                        "X-Requested-With": "XMLHttpRequest",
                    })
            try:
                r = rebot.http_post(line_url,
                                    data=urllib.urlencode(data),
                                    headers=headers,
                                    cookies=cookies)
                res = json.loads(trans_js_str(r.content))
            except:
                result_info.update(result_msg="exception_ok", update_attrs={"left_tickets": 5, "refresh_datetime": now})
                line_log.info("%s\n%s", "".join(traceback.format_exc()), locals())
                return result_info

        update_attrs = {}
        for d in res["data"]:
            if d['SchStat'] == '1':
                drv_datetime = dte.strptime("%s %s" % (d["SchDate"], d["orderbytime"]), "%Y-%m-%d %H:%M")
                line_id_args = {
                    "s_city_name": line.s_city_name,
                    "d_city_name": line.d_city_name,
                    "s_sta_name": d["SchWaitStName"],
                    "d_sta_name": d["SchNodeName"],
                    "crawl_source": line.crawl_source,
                    "drv_datetime": drv_datetime,
                }
                line_id = md5("%(s_city_name)s-%(d_city_name)s-%(drv_datetime)s-%(s_sta_name)s-%(d_sta_name)s-%(crawl_source)s" % line_id_args)
                try:
                    obj = Line.objects.get(line_id=line_id)
                except Line.DoesNotExist:
                    continue
                info = {
                    "full_price": float(d["SchStdPrice"]),
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

    def do_refresh_line_by_app(self, line):
        result_info = {
            "result_msg": "",
            "update_attrs": {},
        }
        line_url = "http://www.vchepiao.cn/mb/base/bus/queryBusSKY"
        params = {
            "fromCity": "深圳",
            "stationCode": line.s_sta_id,
            "dstNode": line.d_city_name,
            "schDate": line.drv_date.replace('-', '')
        }
        headers = {
            "User-Agent": random.choice(BROWSER_USER_AGENT),
            "Content-Type": "application/x-www-form-urlencoded; charset=UTF-8",
            "X-Requested-With": "XMLHttpRequest",
            "accept": "application/json"
        }
        now = dte.now()
        try:
            r = requests.post(line_url,
                              data=urllib.urlencode(params),
                              headers=headers)
            res = r.json()
        except:
            result_info.update(result_msg="exception_ok", update_attrs={"left_tickets": 5, "refresh_datetime": now})
            line_log.info("%s\n%s", "".join(traceback.format_exc()), locals())
            return result_info
        if not res["success"]:
            result_info.update(result_msg="error response", update_attrs={"left_tickets": 0, "refresh_datetime": now})
            return result_info

        update_attrs = {}
        for d in res["data"]["list"]:
            if d['SchStat'] == '1':
                drv_datetime = dte.strptime("%s %s" % (d["SchDate"], d["orderbytime"]), "%Y-%m-%d %H:%M")
                line_id_args = {
                    "s_city_name": line.s_city_name,
                    "d_city_name": line.d_city_name,
                    "s_sta_name": d["SchWaitStName"],
                    "d_sta_name": d["SchNodeName"],
                    "crawl_source": line.crawl_source,
                    "drv_datetime": drv_datetime,
                }
                line_id = md5("%(s_city_name)s-%(d_city_name)s-%(drv_datetime)s-%(s_sta_name)s-%(d_sta_name)s-%(crawl_source)s" % line_id_args)
                try:
                    obj = Line.objects.get(line_id=line_id)
                except Line.DoesNotExist:
                    continue
                info = {
                    "full_price": float(d["SchStdPrice"]),
                    "fee": 0,
                    "left_tickets": int(d["SchSeatCount"]),
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

