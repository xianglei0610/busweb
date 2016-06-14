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
from app.models import Line, ZjgsmWebRebot
from datetime import datetime as dte
from app.utils import md5


class Flow(BaseFlow):

    name = "zjgsm"

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
        rebot = order.get_lock_rebot()
        line = order.line
        # 未登录
        if not login_checked and not rebot.test_login_status():
            lock_result.update({
                "result_code": 2,
                "source_account": rebot.telephone,
                "result_reason": u"账号未登录",
            })
            return lock_result
        lock_result.update(source_account=rebot.telephone)

        # 检验验证码
        headers = {"User-Agent": rebot.user_agent}
        cookies = json.loads(rebot.cookies)
        verify_url = "https://zjgsmwy.com/sso/servlet/checkCode?veryCode=%s&_t=%s" % (valid_code, time.time())
        r = rebot.http_get(verify_url, headers=headers, cookies=cookies)
        res = json.loads(r.content[r.content.index("(")+1: r.content.rindex(")")])
        if res["rtn_code"] != "000000":
            rebot.modify(cookies="{}")
            lock_result.update(result_code=2, result_reason="需要锁票验证码")
            return lock_result
        rtn_key = res["rtn_key"]

        rider_lst = []
        for r in order.riders:
            rider_lst.append("-0-%s-01-%s-%s-false" % (r["name"], r["id_number"], rebot.telephone))

        params = {
            "shift": line.bus_num,
            "startStation": line.extra_info["startstation"],
            "terminalStation": line.extra_info["terminalstation"],
            "offstationcode": line.d_sta_id,
            "startDate": line.drv_date,
            "startTime": line.drv_time,
            "price": "%.2f" % order.order_price,
            "fullprice": "%.2f" % line.full_price,
            "halfprice": "%.2f" % line.half_price,
            "fullTicketNum": order.ticket_amount,
            "halfTicketNum": 0,
            "freeTicketNum": 0,
            "paramcode": rtn_key,
            "phoneCheckCode": valid_code,
            "passengerlist": "@".join(rider_lst),
        }
        ret = self.send_lock_request(order, rebot, params)
        msg = ret["rtnMsg"]
        if ret["rtnCode"] == "000000":
            lock_data = ret["responseData"]
            expire_time = dte.now()+datetime.timedelta(seconds=15*60)
            lock_result.update({
                "result_code": 1,
                "result_reason": msg,
                "raw_order_no": lock_data["orderid"],
                "expire_datetime": expire_time,
                "pay_money": float(lock_data["price"]),
            })
        elif "验证码错误" in msg:
            lock_result.update({
                "result_code": 2,
                "result_reason": msg,
            })
        elif "您当日购票数量" in msg:
            rebot = order.change_lock_rebot()
            lock_result.update({
                "result_code": 2,
                "result_reason": msg,
                "source_account": rebot.telephone,
            })
        else:
            lock_result.update({
                "result_code": 0,
                "result_reason": msg,
            })
        return lock_result

    def send_lock_request(self, order, rebot, data):
        lock_url = "http://www.zjgsmwy.com/busticket/busticket/service/Busticket.orderBusTicket.json"
        headers = {
            "User-Agent": rebot.user_agent,
        }
        cookies = json.loads(rebot.cookies)
        resp = rebot.http_get(lock_url+"?"+urllib.urlencode(data),
                               headers=headers,
                               cookies=cookies)
        ret = resp.json()
        return ret

    def send_order_request(self, order):
        detail_url = "http://www.zjgsmwy.com/busticket/busticket/service/Busticket.getOrderInfo.json"
        rebot = order.get_lock_rebot()
        headers = {
            "User-Agent": rebot.user_agent,
        }
        params = {"orderid": order.raw_order_no}
        cookies = json.loads(rebot.cookies)
        r = rebot.http_get("%s?%s" % (detail_url, urllib.urlencode(params)), headers=headers, cookies=cookies)
        ret = r.json()
        return ret

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

        ret = self.send_order_request(order)
        if ret["rtnCode"] != "000000":
            return
        detail_info = ret["responseData"]["ordervo"]
        state_names = {
            "02": "出票成功",
            "06": "已过期",
            "04": "出票中",
        }
        state = state_names.get(detail_info["state"], "")
        if state == "出票成功":
            pick_no = detail_info["fetchticketcode"]
            pick_code = detail_info["fetchticketkey"]
            dx_info = {
                "time": order.drv_datetime.strftime("%Y-%m-%d %H:%M"),
                "start": order.line.s_sta_name,
                "end": order.line.d_sta_name,
                "code": pick_code,
                "no": pick_no,
                "bus": order.line.bus_num,
            }
            dx_tmpl = DUAN_XIN_TEMPL["江苏"]
            code_list = ["%s|%s" % (pick_no, pick_code)]
            msg_list = [dx_tmpl % dx_info]
            result_info.update({
                "result_code": 1,
                "result_msg": state,
                "pick_code_list": code_list,
                "pick_msg_list": msg_list,
            })
        elif state == "出票中":
            result_info.update({
                "result_code": 4,
                "result_msg": state,
            })
        elif state == "已过期":
            result_info.update({
                "result_code": 5,
                "result_msg": state,
            })
        return result_info

    def get_pay_page(self, order, valid_code="", session=None, pay_channel="alipay" ,**kwargs):
        rebot = ZjgsmWebRebot.objects.get(telephone=order.source_account)
        is_login = rebot.test_login_status()
        ses_key = "pay_login_info"
        if not is_login and valid_code:
            info = json.loads(session[ses_key])
            headers = info["headers"]
            cookies = info["cookies"]
            params = {
                "service": "http://www.zjgsmwy.com/portal/j_spring_cas_security_check;jsessionid=%s" % cookies["JSESSIONID"],
                "renew": "false",
                "appid": "BAS-0512-0001",
                "loginbackurl": "",
                "username": rebot.telephone,
                "password": SOURCE_INFO[SOURCE_ZJGSM]["pwd_encode"][rebot.password],
                "verycode": valid_code,
            }
            jsessionid = cookies["JSESSIONID"]
            login_url = "https://zjgsmwy.com/sso/noflow;jsessionid=%s" % jsessionid
            custom_headers = {}
            custom_headers.update(headers)
            custom_headers.update({"Content-Type": "application/x-www-form-urlencoded;charset=UTF-8"})
            r = rebot.http_post(login_url,
                              data=urllib.urlencode(params),
                              headers=custom_headers,
                              allow_redirects=False,
                              cookies=cookies,)
            cookies.update(dict(r.cookies))
            rebot.modify(cookies=json.dumps(cookies))

        is_login = is_login or rebot.test_login_status()
        if is_login:
            if order.status in [STATUS_LOCK_RETRY, STATUS_WAITING_LOCK]:
                self.lock_ticket(order, valid_code=valid_code, login_checked=is_login)
            if order.status == STATUS_WAITING_ISSUE:
                # step 1
                params = {
                    "service_code": "orderForm",
                    "service_type": "000002",
                    "partner_id": "DFH",
                    "source_id": "01",
                    "pay_channel": "",
                    "pay_method": "",
                    "mer_no": "0001",
                    "mer_info": "苏州汽车客运集团",
                    "order_no": order.raw_order_no,
                    "order_amt": order.pay_money,
                    "order_ccy": "RMB",
                    "order_content": "Ticket orders",
                    "notify_url": "http://www.zjgsmwy.com/busticket/busticket/service/Busticket.toScucess.json",
                    "return_url": "http://www.zjgsmwy.com/busticket/busticket/service/Busticket.pay.do?a=p&b=%s" % order.raw_order_no,
                    "sign_type": "MD5",
                    "GateId": "",
                }
                headers = {"User-Agent": rebot.user_agent}
                url = "http://www.zjgsmwy.com/busticket/busticket/service/Busticket.toSign.json"
                r = rebot.http_get("%s?%s" % (url, urllib.urlencode(params)), headers=headers, cookies=json.loads(rebot.cookies))
                res = r.json()["responseData"]

                # step 2
                url = "http://www.zjgsmwy.com//smartpay/payment/smartpay.do"
                params = {
                    "mer_info": "苏州汽车客运集团",
                    "service_type": "000002",
                    "order_no": order.raw_order_no,
                    "order_amt": order.pay_money,
                    "mer_no": "0001",
                    "service_code": "immPay",
                    "partner_id": "DFH",
                    "source_id": "01",
                    "pay_channel": "alipay",
                    "pay_method": "02",
                    "order_ccy": "RMB",
                    "order_date": res["order_date"],
                    "order_time": res["order_time"],
                    "order_content": "Ticket orders",
                    "citizen_id": res["citizen_id"],
                    "notify_url": "http://www.zjgsmwy.com/busticket/busticket/service/Busticket.toScucess.json",
                    "return_url": "http://www.zjgsmwy.com/busticket/busticket/service/Busticket.pay.do?a=p&b=%s" % order.raw_order_no,
                    "sign_type": "MD5",
                    "signature": res["signature"],
                    "gate_id": "",
                    "instant": "1",
                }
                r = rebot.http_get("%s?%s" % (url, urllib.urlencode(params)), headers=headers, cookies=json.loads(rebot.cookies))
                return {"flag": "html", "content": r.content}

            data = {
                "cookies": json.loads(rebot.cookies),
                "headers": {"User-Agent": rebot.user_agent},
                "valid_url": "https://zjgsmwy.com/sso/servlet/getCode?%s" % time.time(),
            }
            session[ses_key] = json.dumps(data)
            return {"flag": "input_code", "content": ""}
        else:
            headers = {"User-Agent": random.choice(BROWSER_USER_AGENT)}
            index_url = "http://www.zjgsmwy.com/portal/index.jsp"
            r = rebot.http_get(index_url, headers=headers)
            cookies = dict(r.cookies)

            data = {
                "cookies": dict(r.cookies),
                "headers": headers,
                "valid_url": "https://zjgsmwy.com/sso/servlet/getCode?%s" % time.time(),
            }
            session[ses_key] = json.dumps(data)
            return {"flag": "input_code", "content": ""}

    def do_refresh_line(self, line):
        result_info = {
            "result_msg": "",
            "update_attrs": {},
        }
        line_url = "http://www.zjgsmwy.com/busticket/busticket/service/Busticket.getBusTicketList.json"
        params = {
            "AREACODE": line.s_city_id,
            "ONSTAION": line.s_sta_name,
            "OFFSTATION": line.d_city_name,
            "STARTDATE": line.drv_date,
        }
        headers = {
            "User-Agent": random.choice(BROWSER_USER_AGENT),
            "Content-Type": "application/x-www-form-urlencoded;charset=UTF-8",
        }
        r = requests.post(line_url,
                          data=urllib.urlencode(params),
                          headers=headers)
        res = r.json()
        now = dte.now()
        if res["rtnCode"] != "000000":
            result_info.update(result_msg="error response", update_attrs={"left_tickets": 0, "refresh_datetime": now})
            return result_info

        shift_list = res["responseData"]["shiftList"] or []
        update_attrs = {}
        for d in shift_list:
            drv_datetime = dte.strptime("%s %s" % (d["startdate"], d["starttime"]), "%Y%m%d %H%M")
            line_id_args = {
                "s_city_name": line.s_city_name,
                "d_city_name": line.d_city_name,
                "s_sta_name": d["onstation"],
                "d_sta_name": d["offstation"],
                "crawl_source": line.crawl_source,
                "drv_datetime": drv_datetime,
            }
            line_id = md5("%(s_city_name)s-%(d_city_name)s-%(drv_datetime)s-%(s_sta_name)s-%(d_sta_name)s-%(crawl_source)s" % line_id_args)
            try:
                obj = Line.objects.get(line_id=line_id)
            except Line.DoesNotExist:
                continue
            info = {
                "full_price": float(d["price"]),
                "fee": 0,
                "left_tickets": int(d["availablenum"]),
                "refresh_datetime": now,
                "extra_info": {"startstation": d["startstation"], "terminalstation": d["terminalstation"]},
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
