#!/usr/bin/env python
# encoding: utf-8

import json
import urllib
import datetime
import re

from app.constants import *
from app.flow.base import Flow as BaseFlow
from app.models import AnxingWebRebot, Line
from datetime import datetime as dte
from app.utils import md5
from bs4 import BeautifulSoup


class Flow(BaseFlow):

    name = "anxing"

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
        rebot = order.get_lock_rebot()
        is_login = rebot.test_login_status()
        if not is_login:
            for i in range(3):
                if rebot.login() == "OK":
                    is_login = True
                    break
                rebot = order.change_lock_rebot()

        line = order.line
        cookies = json.loads(rebot.cookies)
        # 增加乘客k
        for r in [order.contact_info]+order.riders:
            params = {
                "idcard": r["id_number"],
                "name": r["name"],
                "mobile": r["telephone"],
            }
            headers = {"User-Agent": rebot.user_agent, "Content-Type": "application/x-www-form-urlencoded; charset=UTF-8"}
            headers.update(rebot.http_headers())
            r = rebot.http_post("http://www.anxingbus.com/sell/AddContact", data=urllib.urlencode(params), headers=headers, cookies=cookies)
            res = r.json()
            if not res["isSuccess"] and unicode(res["Message"]) != u"身份证号重复":
                lock_result.update({
                    "result_code": 2,
                    "result_reason": res["Message"],
                    "source_account": rebot.telephone,
                })
                return lock_result

        r = rebot.http_get("http://www.anxingbus.com/sell/getcode", headers=rebot.http_headers(), cookies=cookies)
        code = r.json()["data"]

        params = {
            "busGuid": line.extra_info["BusGuid"],
            "seatTypeID": 1,
            "safeCompanyID": "",
            "Idcards": ",".join([("%s=0" % d["id_number"]) for d in order.riders]),
            "code": code,
            "name": order.contact_info["name"],
            "idcard": order.contact_info["id_number"],
            "mobile": order.contact_info["telephone"],
        }
        headers = {"User-Agent": rebot.user_agent, "Content-Type": "application/x-www-form-urlencoded; charset=UTF-8"}
        headers.update(rebot.http_headers())
        r = rebot.http_post("http://www.anxingbus.com/sell/MakeOrder?", data=urllib.urlencode(params), headers=headers, cookies=cookies)
        res = r.json()
        if res["isSuccess"]:
            expire_time = dte.now()+datetime.timedelta(seconds=20*60)
            lock_result.update({
                "result_code": 1,
                "raw_order_no": res["data"],
                "expire_datetime": expire_time,
                "source_account": rebot.telephone,
            })
        else:
            errmsg = res["Message"]
            code = 2
            if u"锁票异常" in errmsg or u"剩余座位数不足" in errmsg:
                self.close_line(order.line, reason=errmsg)
                code = 0
            lock_result.update({
                "result_code": code,
                "result_reason": errmsg,
                "source_account": rebot.telephone,
            })
        return lock_result

    def send_order_request(self, order):
        url = "http://www.anxingbus.com/sell/GetOrderDetail?orderID=%s" % order.raw_order_no
        rebot = order.get_lock_rebot()
        r = rebot.http_get(url, headers=rebot.http_headers(), cookies=json.loads(rebot.cookies))
        res = r.json()
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
        ret = self.send_order_request(order)
        if not ret["isSuccess"]:
            result_info.update(result_msg="状态未变化")
            return result_info

        state = int(ret["data"]["Status"])
        if state== 4:   # 出票成功
            no, code = ret["data"]["SourceOrderID"], ret["data"]["SourceOrderPass"]
            dx_info = {
                "time": order.drv_datetime.strftime("%Y-%m-%d %H:%M"),
                "start": order.line.s_sta_name,
                "end": order.line.d_sta_name,
                "code": code,
                "no": no,
            }
            dx_tmpl = DUAN_XIN_TEMPL[SOURCE_ANXING]
            code_list = ["%s|%s" % (no, code)]
            msg_list = [dx_tmpl % dx_info]
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
        if not is_login:
            for i in range(3):
                if rebot.login() == "OK":
                    is_login = True
                    break
        if not is_login:
            return {"flag": "error", "content": "账号自动登陆失败，请再次重试!"}

        if order.status in [STATUS_LOCK_RETRY, STATUS_WAITING_LOCK]:
            self.lock_ticket(order)

        if order.status == STATUS_WAITING_ISSUE:
            pay_url = "http://bank.anxingbus.com/Bank/Pay?bussyType=1&orderID=%s&bankType=2" % order.raw_order_no
            r = rebot.http_get(pay_url, headers=rebot.http_headers(), cookies=json.loads(rebot.cookies), allow_redirects=False)
            if u"订单状态发生变化" in r.content:
                return {"flag": "error", "content": "订单状态发生变化,不可支付"}
            pay = float(re.findall(r"total_fee=(\S+)&amp;sign=", r.content)[0])
            no = re.findall(r"out_trade_no=(\S+)&amp;partner=", r.content)[0]
            if no and order.pay_order_no != no:
                order.modify(pay_order_no=no, pay_money=pay,pay_channel='alipay')
            soup = BeautifulSoup(r.content, "lxml")
            url = soup.select_one("a").get("href")
            return {"flag": "url", "content": url}

    def do_refresh_line(self, line):
        result_info = {
            "result_msg": "",
            "update_attrs": {},
        }
        now = dte.now()
        url = "http://www.anxingbus.com/sell/GetBus"
        rebot = AnxingWebRebot.get_one()
        params = {
            "unitID": line.extra_info["UnitID"],
            "busType": 0,
            "cityID": line.s_city_id,
            "sellPlateStationID": "",
            "sellStationID": "",
            #"endCityID": "",
            "endCityID": line.d_city_id,
            #"endStationID": line.d_city_id,
            "endStationID": "",
            "busStartTime": line.drv_date,
            "busEndTime": "%s 23:59:59" % line.drv_date,
            "curPage": 1,
            "pageSize": 1024,
        }
        try:
            r = rebot.http_get("%s?%s" % (url, urllib.urlencode(params)), headers=rebot.http_headers())
            res = r.json()
            detail = res["data"]
        except:
            result_info.update(result_msg="exception_ok", update_attrs={"left_tickets": 5, "refresh_datetime": now})
            return result_info

        update_attrs = {}
        for detail in res["data"]:
            drv_datetime=dte.strptime(detail["BusTime"], "%Y-%m-%d %H:%M")
            line_id_args = {
                "s_city_name": line.s_city_name,
                "d_city_name": line.d_city_name,
                "s_sta_name": detail["SellStationName"],
                "d_sta_name": detail["StationName"],
                "crawl_source": line.crawl_source,
                "drv_datetime": drv_datetime,
            }
            line_id = md5("%(s_city_name)s-%(d_city_name)s-%(drv_datetime)s-%(s_sta_name)s-%(d_sta_name)s-%(crawl_source)s" % line_id_args)
            try:
                obj = Line.objects.get(line_id=line_id)
            except Line.DoesNotExist:
                continue
            extra = line.extra_info
            extra["BusGuid"] = detail["BusGuid"]
            info = {
                "full_price": float(detail["FullPrice"]),
                "fee": 0,
                "left_tickets": int(detail["SeatNum"]),
                "refresh_datetime": now,
                "extra_info": extra,
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
