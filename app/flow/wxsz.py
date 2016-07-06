#!/usr/bin/env python # encoding: utf-8
import requests
import urllib
import datetime
import time
import json

from app.constants import *
from app.flow.base import Flow as BaseFlow
from app.models import Line
from datetime import datetime as dte
from app.utils import md5


class Flow(BaseFlow):

    name = "wxsz"

    def do_lock_ticket(self, order, valid_code=""):
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
        if not rebot.test_login_status():
            lock_result.update({
                "result_code": 2,
                "source_account": rebot.telephone,
                "result_reason": u"账号未登录",
            })
            return lock_result

        if len(set([d["id_number"] for d in order.riders])) != len(order.riders):
            lock_result.update({
                "result_code": 0,
                "source_account": rebot.telephone,
                "result_reason": u"乘客身份证号重复",
            })
            return lock_result
        params = {
            "insurance": 0,
            "uid": rebot.uid,
            "passengers": ",".join(rebot.add_riders(order)),
            "schedulecode": line.bus_num,
            "fromcode": line.s_sta_id,
            "nopay_child_ticket": 0,
            "departdate": line.drv_datetime.strftime("%Y%m%d"),
            "finish_code": line.d_sta_id,
            "from": line.s_sta_name,
            "pay_child_ticket": 0,
            "destination": line.d_sta_name,
        }

        headers = {
            "User-Agent": rebot.user_agent,
            "Content-Type": "application/json;charset=UTF-8",
        }
        lock_url = "http://coach.wisesz.mobi/coach_v38/main/confirm_order"
        lock_url= "%s?%s" % (lock_url, urllib.urlencode(params))
        r = rebot.http_post(lock_url, headers=headers)
        ret = r.json()
        msg = ret["errorMsg"]
        if ret["errorCode"] == 0:
            expire_time = dte.now()+datetime.timedelta(seconds=15*60)
            lock_result.update({
                "result_code": 1,
                "result_reason": msg,
                "raw_order_no": "",
                "expire_datetime": expire_time,
                "pay_money": 0,
                "lock_info": {"order_id": ret["data"]["ord_id"]},
                "source_account": rebot.telephone,
            })
        elif u"账户异常" in msg:
            rebot = order.change_lock_rebot()
            lock_result.update({
                "result_code": 2,
                "source_account": rebot.telephone,
                "result_reason": msg,
            })
        else:
            if u"所购车次已无余票" in msg:
                self.close_line(line, reason=msg)
            lock_result.update({
                "result_code": 0,
                "result_reason": msg,
                "source_account": rebot.telephone,
            })
        return lock_result

    def send_order_request(self, order):
        detail_url = "http://coach.wisesz.mobi/coach_v38/order/ondetail"
        rebot = order.get_lock_rebot()
        headers = {
            "User-Agent": rebot.user_agent,
            "Content-Type": "application/x-www-form-urlencoded",
        }
        params = {
            "sign": rebot.sign,
            "uid": rebot.uid,
            "id": order.lock_info["order_id"],
            "ordsn": "",
        }
        r = rebot.http_get("%s?%s" % (detail_url, urllib.urlencode(params)), headers=headers)
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
        if ret["errorCode"] != 0:
            return
        detail_info = ret["data"]
        if order.raw_order_no != detail_info["order_sn"]:
            order.modify(raw_order_no=detail_info["order_sn"],
                         pay_order_no=detail_info["pay_sn"],
                         pay_money=float(detail_info["total_price"]))

        status = detail_info["status"]
        state_names = {
            "2": "过期取消",
            "1": "出票成功",
        }
        state = state_names.get(status, "")
        if state == "出票成功":
            pick_no = detail_info["ticket_number"]
            pick_code = detail_info["ticket_password"]
            dx_info = {
                "time": order.drv_datetime.strftime("%Y-%m-%d %H:%M"),
                "start": order.line.s_sta_name,
                "end": order.line.d_sta_name,
                "code": pick_code,
                "no": pick_no,
                "raw_order": order.raw_order_no,
            }
            dx_tmpl = DUAN_XIN_TEMPL[SOURCE_WXSZ]
            code_list = ["%s|%s" % (pick_no, pick_code)]
            msg_list = [dx_tmpl % dx_info]
            result_info.update({
                "result_code": 1,
                "result_msg": state,
                "pick_code_list": code_list,
                "pick_msg_list": msg_list,
            })
        elif state == "过期取消":
            result_info.update({
                "result_code": 5,
                "result_msg": state,
            })
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
                url = "http://apppay.wisesz.mobi/payment_mobile/order/set_pay"
                st = str(int(time.time()*1000))
                self.refresh_issue(order)
                order.reload()
                pay_sn = order.pay_order_no
                params = {
                    "sign": md5(pay_sn+st),
                    "uid": rebot.uid,
                    "pay_source": 3,
                    "platform": 2,
                    "pwd": "",
                    "use_coupon": "",
                    "time": st,
                    "appVersion": "3.9.1",
                    "order_sn": pay_sn,
                    "use_wallet": 0,
                    "deviceId": "" ,
                    "version": "3.9.1",
                }
                headers = {
                    "User-Agent": rebot.user_agent,
                    "Content-Type": "application/x-www-form-urlencoded",
                }
                r = rebot.http_post(url, headers=headers, data=urllib.urlencode(params))
                res = r.json()
                if res["errorCode"] != 0:
                    return {"flag": "error", "content": json.dumps(res, ensure_ascii=False)}
                order.update(pay_channel='alipay')
                return {"flag": "url", "content": res["data"]["url"]}
        else:
            return {"flag": "error", "content": u"账号登录失败"}

    def do_refresh_line(self, line):
        result_info = {
            "result_msg": "",
            "update_attrs": {},
        }
        line_url = "http://coach.wisesz.mobi/coach_v38/main/get_tickets"
        name_trans = {
            u"苏州北广场站": u"北广场站",
            u"苏州吴中站": u"吴中站",
        }
        params = {
            "departdate": line.drv_datetime.strftime("%Y%m%d"),
            "destination": line.d_city_name,
            "fromcode": line.s_sta_id,
            "from": name_trans.get(line.s_sta_name, line.s_sta_name),
        }
        headers={
            "User-Agent": "Apache-HttpClient/UNAVAILABLE (java 1.4)",
            "Content-Type": "application/json;charset=UTF-8"
        }
        now = dte.now()
        line_url = "%s?%s" % (line_url, urllib.urlencode(params))
        try:
            r = requests.post(line_url, headers=headers, timeout=10)
            res = r.json()
        except:
            result_info.update(result_msg="exception_ok", update_attrs={"left_tickets": 5, "refresh_datetime": now})
            return result_info

        if res["errorCode"] != 0:
            result_info.update(result_msg="error response", update_attrs={"left_tickets": 0, "refresh_datetime": now})
            return result_info

        shift_list = res["data"]["dataList"] or []
        update_attrs = {}
        for d in shift_list:
            drv_datetime = dte.strptime("%s %s" % (d["FIELDS1"], d["FIELDS3"]), "%Y%m%d %H%M")
            line_id_args = {
                "s_city_name": line.s_city_name,
                "d_city_name": line.d_city_name,
                "s_sta_name": d["FIELDS4"],
                "d_sta_name": d["FIELDS5"],
                "crawl_source": line.crawl_source,
                "drv_datetime": drv_datetime,
            }
            line_id = md5("%(s_city_name)s-%(d_city_name)s-%(drv_datetime)s-%(s_sta_name)s-%(d_sta_name)s-%(crawl_source)s" % line_id_args)
            try:
                obj = Line.objects.get(line_id=line_id)
            except Line.DoesNotExist:
                continue
            info = {
                "full_price": float(d["FIELDS14"]),
                "fee": 0,
                "left_tickets": int(d["FIELDS10"]),
                "refresh_datetime": now,
                "extra_info": {"startstation": d["FIELDS17"], "terminalstation": d["FIELDS6"]},
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
