#!/usr/bin/env python
# encoding: utf-8

import random
import requests
import json
import urllib
import datetime

from app.constants import *
from app.flow.base import Flow as BaseFlow
from app.models import Line, TCWebRebot, Order
from datetime import datetime as dte
from app.utils import md5
from bs4 import BeautifulSoup


class Flow(BaseFlow):

    name = "tongcheng"

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
        with TCWebRebot.get_and_lock(order) as rebot:
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
                    "result_reason": "账号未登录",
                })
                return lock_result


            # 构造表单参数
            cookies = json.loads(rebot.cookies)
            riders = []
            for r in order.riders:
                riders.append({
                    "name": r["name"],
                    "IDType": "1",
                    "IDCard": r["id_number"],
                    "passengersType": "1",
                    "IsLinker": False,
                })
            data = {
                "MemberId": cookies["us"],
                "TotalAmount": order.order_price,
                "InsuranceId": "",
                "InsuranceAmount": 0,
                "TicketsInfo": [
                    {
                        "CoachType": line.vehicle_type,
                        "CoachNo": line.bus_num,
                        "Departure": line.s_city_name,
                        "Destination": line.d_city_name,
                        "dptStation": line.s_sta_name,
                        "ArrStation": line.d_sta_name,
                        "dptDateTime": "%sT%s:00" % (line.drv_date, line.drv_time),
                        "DptDate": line.drv_date,
                        "dptTime": line.drv_time,
                        "ticketPrice": line.full_price,
                        "OptionType": 1,
                    }
                ],
                "ContactInfo": {
                    "Name": order.contact_info["name"],
                    "MobileNo": order.contact_info["telephone"],
                    "IDType": 1,
                    "IDCard": order.contact_info["id_number"],
                },
                "PassengersInfo": riders,
                "Count": order.ticket_amount,
                "StationCode": line.s_sta_id,
                "ticketFee": 0
            }
            ret = self.send_lock_request(order, rebot, data)
            ret = ret["response"]
            desc = ret["body"]["RspCode_0000"]
            if ret["header"]["rspDesc"] == "0000":
                expire_time = dte.now()+datetime.timedelta(seconds=20*60)
                lock_result.update({
                    "result_code": 1,
                    "result_reason": desc,
                    "pay_url": ret["body"]["PayUrl"],
                    "raw_order_no": self.query_order_no(order, rebot),
                    "expire_datetime": expire_time,
                    "source_account": rebot.telephone,
                    "pay_money": float(ret["body"]["TotalFee"]),
                })
            else:
                lock_result.update({
                    "result_code": 0,
                    "result_reason": desc,
                    "pay_url": "",
                    "raw_order_no": "",
                    "expire_datetime": None,
                    "source_account": rebot.telephone,
                })
            return lock_result

    def send_lock_request(self, order, rebot, data):
        """
        单纯向源站发请求
        """
        submit_url = "http://bus.ly.com/Order/CreateBusOrder"
        headers = {
            "User-Agent": rebot.user_agent,
            "Content-Type": "application/json",
        }
        cookies = json.loads(rebot.cookies)
        resp = requests.post(submit_url,
                             data=json.dumps(data),
                             headers=headers,
                             cookies=cookies)
        ret = resp.json()
        return ret

    def query_order_no(self, order, rebot):
        """
        去源站拿订单号
        """
        url = "http://member.ly.com/ajaxhandler/OrderListHandler.ashx?OrderFilter=1&ProjectTag=0&DateType=2&PageIndex=1"
        headers = {"User-Agent": rebot.user_agent}
        cookies = json.loads(rebot.cookies)
        r = requests.get(url, headers=headers, cookies=cookies)
        res = r.json()
        line = order.line
        for info in res["OrderDetailList"]:
            order_no = info["SerialId"]
            bus_num = info["CoachNo"]
            if bus_num != line.bus_num:
                continue

            # 该订单已经有主了
            if Order.objects.filter(crawl_source=order.crawl_source, raw_order_no=order_no):
                continue

            detail = self.send_order_request(rebot, order_no)
            if detail["drv_datetime"] != order.drv_datetime:
                continue
            if detail["contact_name"] != order.contact_info["name"]:
                continue
            if detail["contact_phone"] != order.contact_info["telephone"]:
                continue
            return order_no
        return ""


    def send_order_request(self, rebot, raw_order_no):
        detail_url = "http://member.ly.com/bus/order/orderDetail?id=%s" % raw_order_no
        headers = {
            "User-Agent": rebot.user_agent,
        }
        cookies = json.loads(rebot.cookies)
        r = requests.get(detail_url, headers=headers, cookies=cookies)
        soup = BeautifulSoup(r.content, "lxml")

        state = soup.select(".paystate")[0].get_text().strip()
        sdate = soup.select(".list01_info table")[0].findAll("tr")[2].get_text().strip()
        drv_datetime = dte.strptime(sdate, "%Y-%m-%d %H:%M:%S")
        contact_lst = soup.select(".list01_info table")[3].select("td")
        contact_name = contact_lst[0].lstrip("姓名：").strip()
        contact_phone = contact_lst[1].lstrip("手机：").strip()

        return {
            "state": state,
            "drv_datetime": drv_datetime,
            "contact_name": contact_name,
            "contact_phone": contact_phone,
            "pick_no": "",
            "pick_code": "",
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
        rebot = TCWebRebot.objects.get(telephone=order.source_account)
        ret = self.send_order_request(rebot, order=order)
        state = ret["state"]
        if state == "支付超时作废":
            result_info.update({
                "result_code": 5,
                "result_msg": state,
            })
        elif state == "已作废":
            result_info.update({
                "result_code": 2,
                "result_msg": state,
            })
        elif state=="出票异常":
            result_info.update({
                "result_code": 2,
                "result_msg": state,
            })
        elif state=="购票成功":
            no, code, site = ret["pick_no"], ret["pick_code"], ret["pick_site"]
            dx_info = {
                "time": order.drv_datetime.strftime("%Y-%m-%d %H:%M"),
                "start": order.line.s_sta_name,
                "end": order.line.d_sta_name,
                "code": code,
                "no": no,
                "site": site,
            }
            dx_tmpl = DUAN_XIN_TEMPL[SOURCE_BABA]
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
        rebot = TCWebRebot.objects.get(telephone=order.source_account)
        if valid_code:
            info = json.loads(session["pay_login_info"])
            headers = info["headers"]
            cookies = info["cookies"]
            rebot.login(headers=headers, cookies=cookies, valid_code=valid_code)

        is_login = rebot.test_login_status()
        if is_login:
            if order.status == STATUS_LOCK_RETRY:
                self.lock_ticket(order)
            if order.status == STATUS_WAITING_ISSUE:
                return {"flag": "url", "content": order.pay_url}
        else:
            login_form = "https://passport.ly.com"
            valid_url = "https://passport.ly.com/AjaxHandler/ValidCode.ashx?action=getcheckcode&name=%s" % rebot.telephone
            headers = {"User-Agent": random.choice(BROWSER_USER_AGENT)}
            r = requests.get(login_form, headers=headers)
            data = {
                "cookies": dict(r.cookies),
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
        line_url = "http://m.ly.com/bus/BusJson/BusSchedule"
        params = dict(
            Departure=line.s_city_name,
            Destination=line.d_city_name,
            DepartureDate=line.drv_date,
            DepartureStation="",
            DptTimeSpan=0,
            HasCategory="true",
            Category="0",
            SubCategory="",
            ExParms="",
            Page="1",
            PageSize="1025",
            BookingType="0"
        )
        headers = {
            "User-Agent": random.choice(BROWSER_USER_AGENT),
            "Content-Type": "application/x-www-form-urlencoded",
        }
        r = requests.post(line_url, data=urllib.urlencode(params), headers=headers)
        res = r.json()
        res = res["response"]
        now = dte.now()
        if res["rspCode"] != "0000":
            result_info.update(result_msg="error response", update_attrs={"left_tickets": 0, "refresh_datetime": now})
            return result_info

        update_attrs = {}
        for d in res["body"]["schedule"]:
            drv_datetime = dte.strptime("%s %s" % (d["dptDate"], d["dptTime"]), "%Y-%m-%d %H:%M")
            line_id_args = {
                "s_city_name": line.s_city_name,
                "d_city_name": line.d_city_name,
                "bus_num": d["coachNo"],
                "crawl_source": line.crawl_source,
                "drv_datetime": drv_datetime,
            }
            line_id = md5("%(s_city_name)s-%(d_city_name)s-%(drv_datetime)s-%(bus_num)s-%(crawl_source)s" % line_id_args)
            try:
                obj = Line.objects.get(line_id=line_id)
            except Line.DoesNotExist:
                continue
            info = {
                "full_price": float(d["ticketPrice"]),
                "fee": 0,
                "left_tickets": int(d["ticketLeft"]),
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
