#!/usr/bin/env python
# encoding: utf-8

import random
import json
import urllib
import datetime
import requests
import time
import re

from app.constants import *
from app.flow.base import Flow as BaseFlow
from app.models import Line
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
            "endcity": line.extra_info["endcity"],
            "endnode": line.extra_info["endnodename"],
            "fromcity": line.s_city_name,
            "mobile": rebot.telephone,
            "nonce": rd,
            "orderno": "",
            "paytype": "alipay",
            "price": str(line.real_price()),
            "psw": rebot.password,
            "schcode": line.bus_num,
            "schdate": line.drv_datetime.strftime("%Y%m%d"),
            "sendtime": line.drv_datetime.strftime("%H%M"),
            "signature": rebot.get_signature(ts, rd),
            "startcity": line.d_city_name,
            "startstation": line.s_sta_id,
            "startstationname": line.s_sta_name,
            "subject": "%s到%s" % (line.s_city_name, line.d_city_name),
            "timestamp": ts,
            "tkcount": str(order.ticket_amount),
            "tocity": line.d_city_name
        }

        rider_info = {
            "certno": order.contact_info["id_number"],
            "certtype": "1",
            "mobile": order.contact_info["telephone"],
            "name": order.contact_info["name"],
            "passengertype": "1"
        }
        # 锁票提交的参数
        lock_params = {}
        lock_params.update(base)
        lock_params.update({
            "createtime": ts,
            "cust": rider_info,
            "passengerlist": [rider_info],
        })

        # url带的参数
        url_pramas = {"token": rebot.token}
        url_pramas.update(base)
        url = "http://www.gdnyt.cn/api/ticketorder/lockticket/?"+urllib.urlencode(url_pramas)
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
        errmsg = ret["errmsg"]
        if ret.get("success", False):
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
        elif u"班次不在预售期" in errmsg or u"没有余票" in errmsg or u"该班次在客运站发生了变动" in errmsg or u"锁票失败了 ╮囧╭ 请您再试一次" in errmsg:
            self.close_line(order.line, reason=errmsg)
            lock_result.update({
                "result_code": 0,
                "result_reason": errmsg,
                "source_account": rebot.telephone,
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
        rebot = order.get_lock_rebot()
        url = "http://183.6.161.195:9000/api/TicketOrder/QueryOrder?token=%s" % rebot.token     # 已完成
        data = {}
        headers = {
            "User-Agent": rebot.user_agent,
            "Content-Type": "application/json;charset=utf-8",
        }
        r = rebot.http_post(url, data=json.dumps(data), headers=headers)
        return r.json()

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
        if not ret.get("success", False):
            result_info.update(result_msg=ret.get("errmsg", ""))
            return result_info
        detail = {}
        for d in ret["data"]:
            if d["orderno"] == order.raw_order_no:
                detail = d
                break
        if not detail:
            result_info.update(result_msg="未查到已完成订单")
            return result_info

        state = detail["orderstatus"]
        if state=="成功":
            pick_code = detail["ticketsecret"]
            dx_info = {
                "time": order.drv_datetime.strftime("%Y-%m-%d %H:%M"),
                "start": order.line.s_sta_name,
                "end": order.line.d_sta_name,
                "code": pick_code,
                'raw_order': order.raw_order_no,
            }
            dx_tmpl = DUAN_XIN_TEMPL[SOURCE_GDSW]
            pick_msg = dx_tmpl % dx_info
            result_info.update({
                "result_code": 1,
                "result_msg": state,
                "pick_code_list": [pick_code],
                "pick_msg_list": [pick_msg],
            })
        elif state == "已退款":
            result_info.update({
                "result_code": 3,
                "result_msg": state,
            })
        elif state=="出票失败":
            result_info.update({
                "result_code": 2,
                "result_msg": state,
            })
        return result_info

    def do_refresh_issue(self, order):
        return self.do_refresh_issue_by_web(order)

    def do_refresh_issue_by_web(self, order):
        result_info = {
            "result_code": 0,
            "result_msg": "",
            "pick_code_list": [],
            "pick_msg_list": [],
        }
        if not self.need_refresh_issue(order):
            result_info.update(result_msg="状态未变化")
            return result_info
        if not order.lock_info.get("data", {}):
            result_info.update(result_msg="lock_info没内容")
            return result_info
        detail = order.lock_info["data"][0]
        key, orderno = detail["transid"], detail["orderno"]
        if orderno != order.raw_order_no:
            result_info.update(result_msg="lock_info内容异常,订单号不一致")
            return result_info
        url = "http://ticket.gdcd.gov.cn/OrderDetail.aspx?OrderNo=%s&Key=%s" % (orderno, key)
        rebot = order.get_lock_rebot()
        r = rebot.http_get(url, headers={"User-Agent": random.choice(BROWSER_USER_AGENT)})
        if r.status_code != 200:
            result_info.update(result_msg="请求异常,返回%s" % r.status_code)
            return result_info
        soup = BeautifulSoup(r.content, "lxml")
        try:
            status_msg = soup.select_one("#MainContent_lblOrderPayResult").text.encode("utf-8")
            pick_text = soup.select_one("#lblOrderMessage").text.encode("utf-8")
            pick_code = re.findall(r"取票密码：(\d+)", pick_text)[0]
            if u"已出票" in status_msg:
                dx_info = {
                    "time": order.drv_datetime.strftime("%Y-%m-%d %H:%M"),
                    "start": order.line.s_sta_name,
                    "end": order.line.d_sta_name,
                    "code": pick_code,
                    'raw_order': order.raw_order_no,
                }
                dx_tmpl = DUAN_XIN_TEMPL[SOURCE_GDSW]
                pick_msg = dx_tmpl % dx_info
                result_info.update({
                    "result_code": 1,
                    "result_msg": status_msg,
                    "pick_code_list": [pick_code],
                    "pick_msg_list": [pick_msg],
                })
        except Exception, e:
            pass
        return result_info


    def get_pay_page(self, order, valid_code="", session=None, pay_channel="alipay" ,**kwargs):
        rebot = order.get_lock_rebot()
        is_login = rebot.test_login_status()
        if not is_login:
            is_login = (rebot.login() == "OK")

        if is_login:
            if order.status in [STATUS_LOCK_RETRY, STATUS_WAITING_LOCK]:
                self.lock_ticket(order)
            if order.status == STATUS_WAITING_ISSUE:
                no, pay = "", 0
                for s in order.pay_url.split("?")[1].split("&"):
                    k, v = s.split("=")
                    if k == "out_trade_no":
                        no = v
                    elif k == "total_fee":
                        pay = float(v)
                if no and order.pay_order_no != v:
                    order.modify(pay_order_no=v, pay_money=pay)
                return {"flag": "url", "content": order.pay_url}
        else:
            return {"flag": "error", "content": u"账号登录失败"}

    def _get_query_period(self, line):
        t = line.drv_datetime.strftime("%H%M")
        lst = [
            ("0600", "1200"),
            ("1200", "1400"),
            ("1400", "1800"),
            ("1800", "2359"),
        ]
        for s, e in lst:
            if s<=t<e:
                return s, e
        return "", ""

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
            "tocity": line.d_city_name,
            # "tocity": line.d_sta_name,
        }
        headers={"Content-Type": "application/json; charset=UTF-8", "User-Agent": random.choice(MOBILE_USER_AGENG)}
        try:
            r = requests.post(url, data=json.dumps(params), headers=headers)
            res = r.json()
        except:
            result_info.update(result_msg="exception_ok", update_attrs={"left_tickets": 1, "refresh_datetime": now})
            return result_info

        if not res.get("success", False):
            result_info.update(result_msg="error response %s" % res.get("errmsg", ""), update_attrs={"left_tickets": 0, "refresh_datetime": now})
            return result_info

        update_attrs = {}
        for d in res["data"]:
            if not d["sell"]:
                continue
            drv_datetime = dte.strptime("%s %s" % (d["schdate"], d["sendtime"]), "%Y%m%d %H%M")
            line_id_args = {
                "s_city_name": res["startcity"],
                "d_city_name": line.d_city_name,
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
                "extra_info": {"endnodename": d["endnodename"], "endnodecode": d["endnodecode"], "endcity": d["endcity"]},
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
