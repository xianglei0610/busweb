#!/usr/bin/env python
# encoding: utf-8

import random
import json
import urllib
import urllib2
import datetime
import requests
import time

from app.constants import *
from app.flow.base import Flow as BaseFlow
from app.models import Line, TCWebRebot, Order, TCAppRebot
from datetime import datetime as dte
from app.utils import md5
from bs4 import BeautifulSoup


class Flow(BaseFlow):

    name = "gdsw"

    def get_lock_request_info(self, order):
        line = order.line
        rebot = order.get_lock_rebot()
        ts = str(int(time.time()))
        rd = str(random.random())

        base = {
            "appid": "andio_95C429257",
            "dstnode": line.d_sta_id,
            "endcity": line.d_city_name,
            "endnode": line.d_sta_name,
            "fromcity": line.s_city_name,
            "mobile": rebot.telephone,      # 不确定这个是不是注册人电话
            "nonce": rd,
            "orderno": "",
            "paytype": "alipay",
            "price": str(line.real_price()*order.ticket_amount()),
            "psw": rebot.password,
            "schcode": line.bus_num,
            "schdate": line.drv_datetime.strftime("%Y%m%d"),
            "sendtime": line.drv_datetime.strftime("%H%M"),
            "signature": rebot.get_signature(ts, rd),
            "startcity": line.s_city_name,
            "startstation": line.s_sta_id,
            "startstationname": line.s_sta_name,
            "subject": "%s到%s" % (line.s_city_name, line.d_city_name),
            "timestamp": ts,
            "tkcount": str(order.ticket_amount),
            "tocity": line.d_city_name
        }

        riders = []
        for d in order.riders:
            riders.append({
                "certno": d["id_number"],
                "certtype": "1",
                "mobile": d["telephone"],
                "name": d["name"],
                "passengertype": "1"
            })

        # 锁票提交的参数
        lock_params = {}
        lock_params.upate(base)
        lock_params.upadte({
            "createtime": ts,
            "cust": {
                "certno": order.contact_info["id_number"],
                "certtype": "1",
                "mobile": order.contact_info["telephone"],
                "name": order.contact_info["name"],
                "passengertype": "1"
            },
            "passengerlist": riders,
        })

        # url带的参数
        url_pramas = {}
        url_pramas.update(base)
        url_pramas.update(token=rebot.token)
        url = "http://www.gdnyt.cn/api/ticketorder/lockticket?"+urllib.urlencode(url_pramas)
        return url, lock_params


    def do_lock_ticket_by_app(self, order):
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

        url, data = self.get_lock_request_info(order)
        headers = {
            "User-Agent": rebot.user_agent,
            "Content-Type": "application/json;charset=utf-8",
        }
        r = rebot.http_post(url, data=json.dumps(data), headers=headers)
        ret = r.json()
        errmsg = res["errmsg"]
        if ret["success"]:
            expire_time = dte.now()+datetime.timedelta(seconds=20*60)
            lock_result.update({
                "result_code": 1,
                "result_reason": errmsg,
                "pay_url": ret["paydata"]["payurl"],
                "raw_order_no":  ret["data"][0]["orderno"],
                "expire_datetime": expire_time,
                "source_account": rebot.telephone,
                "lock_info": ret,
            })
        else:
            lock_result.update({
                "result_code": 2,
                "result_reason": errmsg,
                "source_account": rebot.telephone,
            })
        return lock_result

    def do_lock_ticket(self, order):
        return self.do_lock_ticket_by_app(order)

    def send_order_request_by_app(self, order):
        rebot = TCAppRebot.objects.get(telephone=order.source_account)
        data = {
            "memberid": rebot.user_id,
            "orderId": order.lock_info["orderId"],
        }
        url = "http://tcmobileapi.17usoft.com/bus/OrderHandler.ashx"
        r = rebot.http_post(url, "getbusorderdetail", data)
        return r.json()["response"]

    def do_refresh_issue_by_app(self, order):
        result_info = {
            "result_code": 0,
            "result_msg": "",
            "pick_code_list": [],
            "pick_msg_list": [],
        }
        if not self.need_refresh_issue(order):
            result_info.update(result_msg="状态未变化")
            return result_info
        ret = self.send_order_request_by_app(order)
        desc = ret["header"]["rspDesc"]
        if ret["header"]["rspCode"] != "0000":
            result_info.update(result_msg=desc)
            return result_info
        state = ret["body"]["orderStateName"]
        if state == "出票中":
            result_info.update({
                "result_code": 4,
                "result_msg": state,
            })
        elif state == "已取消":
            result_info.update({
                "result_code": 5,
                "result_msg": state,
            })
        elif state=="出票成功":
            body = ret["body"]
            result_info.update({
                "result_code": 1,
                "result_msg": state,
                "pick_code_list": ["%s|%s" % (body["getTicketNo"], body["getTicketPassWord"])],
                "pick_msg_list": [body["getTicketInfo"]],
            })
        elif state == "已退款":
            result_info.update({
                "result_code": 3,
                "result_msg": state,
            })
        elif state=="出票失败":
            self.close_line(order.line, "出票失败")
            result_info.update({
                "result_code": 2,
                "result_msg": state,
            })
        return result_info

    def do_refresh_issue(self, order):
        return self.do_refresh_issue_by_app(order)

    def get_pay_page(self, order, valid_code="", session=None, pay_channel="alipay" ,**kwargs):
        if not order.source_account:
            rebot = order.get_lock_rebot()
        rebot = TCWebRebot.objects.get(telephone=order.source_account)
        if valid_code:
            info = json.loads(session["pay_login_info"])
            headers = info["headers"]
            cookies = info["cookies"]
            rebot.login(headers=headers, cookies=cookies, valid_code=valid_code)

        is_login = rebot.test_login_status()
        if is_login:
            if order.status in [STATUS_LOCK_RETRY, STATUS_WAITING_LOCK]:
                self.lock_ticket(order)
            if order.status == STATUS_WAITING_ISSUE:
                headers = {
                    "User-Agent": rebot.user_agent,
                    "Content-Type": "application/x-www-form-urlencoded",
                }
                form_str = "OrderId=%s&TotalAmount=%s" % (order.lock_info["orderId"], order.order_price)
                r = rebot.http_post("http://member.ly.com/bus/Pay/MobileGateway",
                                     data=form_str,
                                     headers=headers,
                                     cookies=json.loads(rebot.cookies))
                try:
                    res = r.json()["response"]
                except Exception, e:
                    rebot.modify(ip="")
                    raise e
                if res["header"]["rspCode"] == "0000":
                    pay_url = res["body"]["PayUrl"]
                    # return {"flag": "url", "content": pay_url}

                    r = rebot.http_get(pay_url, headers=headers, verify=False)
                    content = r.content
                    soup = BeautifulSoup(content, "lxml")
                    sign = soup.select("#aliPay")[0].get("data-sign")
                    partner = soup.find("input", attrs={"name": "partner"}).get("value")
                    serial = soup.find("input", attrs={"name": "serial"}).get("value")
                    pay_type = soup.select("#aliPay")[0].get("data-value")
                    params = {
                        "sign": sign,
                        "partner": partner,
                        "serial": serial,
                        "pay_data": pay_type,
                    }
                    alipay_url = "https://pay.ly.com/pc/payment/GatewayPay"
                    form_str = urllib.urlencode(params)
                    r = rebot.http_post(alipay_url, headers=headers, data=form_str, verify=False)
                    res = r.json()

                    web_url = res["web_url"]
                    parser = urllib2.urlparse.urlparse(web_url)
                    data = {}
                    for s in parser.query.split("&"):
                        n, v = s.split("=")
                        data[n] = v
                    pay_money = float(data["total_fee"])
                    trade_no = data["out_trade_no"]
                    if order.pay_money != pay_money or order.pay_order_no != trade_no:
                        order.modify(pay_money=pay_money, pay_order_no=trade_no)
                    return {"flag": "url", "content": web_url}
                return {"flag": "html", "content": r.content}
        else:
            login_form = "https://passport.ly.com"
            valid_url = "https://passport.ly.com/AjaxHandler/ValidCode.ashx?action=getcheckcode&name=%s" % rebot.telephone
            headers = {"User-Agent": random.choice(BROWSER_USER_AGENT)}
            r = rebot.http_get(login_form, headers=headers, verify=False)
            data = {
                "cookies": dict(r.cookies),
                "headers": headers,
                "valid_url": valid_url,
            }
            session["pay_login_info"] = json.dumps(data)
            return {"flag": "input_code", "content": ""}

    def _get_query_period(self, line):
        t = line.drv_datetime.strftime("%H%M")
        lst = [
            ("0600", "1200"),
            ("1200", "1400"),
            ("1400", "1800"),
            ("1800", "2400"),
        ]
        for s, e in lst:
            if s<=t<e:
                return s, e
        return "0600" , "2400"

    def do_refresh_line(self, line):
        result_info = {"result_msg": "","update_attrs": {},}
        url = "http://183.6.161.195:9000/api/TicketOrder/QuerySchedule"
        now = dte.now()

        stime, etime = self._get_query_period(line)
        params = {
            "fromcity": line.s_city_name,
            "schdate": line.drv_datetime.strftime("%Y%m%d"),
            "schtimeend": etime,
            "schtimestart": stime,
            #"tocity": line.d_city_name,
            "tocity": line.d_sta_name,
        }
        headers={"Content-Type": "application/json; charset=UTF-8", "User-Agent": random.choice(MOBILE_USER_AGENG)}
        try:
            r = requests.post(url, data=json.dumps(params), headers=headers)
            res = r.json()
        except:
            result_info.update(result_msg="exception_ok", update_attrs={"left_tickets": 1, "refresh_datetime": now})
            return result_info

        if not res.get("success", False):
            result_info.update(result_msg="error response", update_attrs={"left_tickets": 0, "refresh_datetime": now})
            return result_info

        update_attrs = {}
        for d in res["data"]:
            if not d["sell"]:
                continue
            drv_datetime = dte.strptime("%s %s" % (d["schdate"], d["sendtime"]), "%Y%m%d %H%M")
            line_id_args = {
                "s_city_name": res["startcity"],
                "d_city_name": d["endcity"],
                "s_sta_name": d["startstationname"],
                "d_sta_name": d["endstationname"],
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
                "left_tickets": int(d["lefttickets"]),
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
