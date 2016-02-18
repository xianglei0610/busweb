#!/usr/bin/env python
# encoding: utf-8
import time
import json
import requests
import urllib
import random
import datetime

from app.constants import *
from app import config
from app.flow.base import Flow as BaseFlow
from app.utils import md5
from datetime import datetime as dte
from app.models import Line


class Flow(BaseFlow):

    name = "fangbian"

    def post_data_templ(self, service_id, sdata):
        ts = int(time.time())
        code = "car12308com"
        key = "car12308com201510"
        tmpl = {
            "merchantCode": code,
            "version": "1.4.0",
            "timestamp": ts,
            "serviceID": service_id,
            "data": sdata,
            "sign": md5("%s%s%s%s%s" % (code, service_id, ts, sdata, md5(key))),
        }
        return tmpl

    def post_headers(self):
        headers = {
            "User-Agent": random.choice(BROWSER_USER_AGENT),
            "Content-Type": "application/x-www-form-urlencoded",
        }
        return headers

    def do_lock_ticket(self, order):
        lock_result = {
            "lock_info": {},
            "source_account": "",
            "result_code": 0,
            "result_reason": "",
            "pay_url": "",
            "raw_order_no": "",
            "expire_datetime": "",
            "pay_money": 0,
        }
        line = order.line
        riders = []
        for d in order.riders:
            riders.append({
                "name": d["name"],
                "IDCard": d["id_number"],
                "mobileNo": d["telephone"],
                "passengerType": 1,
                "IDType": 1
            })
        params = {
            "merchantOrderNo": order.order_no,
            "stationCode": line.s_sta_id,
            "ticketsInfo": [
                {
                    "coachNo": line.bus_num,
                    "departure": line.s_city_name,
                    "dptStation": line.s_sta_name,
                    "destination": line.d_city_name,
                    "arrStation": line.d_sta_name,
                    "dptDate": line.drv_date,
                    "dptTime": line.drv_time,
                    "ticketPrice": line.full_price,
                    "optionType": 1
                },
            ],
            "contactInfo": {
                "name": order.contact_info["name"],
                "IDCard": order.contact_info["id_number"],
                "mobileNo": order.contact_info["telephone"],
            },
            "passengersInfo": riders,
            "exData1": line.extra_info["exData1"],
            "exData2": line.extra_info["exData2"],
            "callBackUrl": "http://d.12308.com/fangbian/callback"
        }
        fd = self.post_data_templ("U0201", json.dumps(params))
        url = config.FANGBIAN_API_URL + "/Order"
        r = requests.post(url, data=urllib.urlencode(fd), headers=self.post_headers())
        ret = r.json()
        code = ret["code"]
        if code == 2101:
            expire_time = dte.now()+datetime.timedelta(seconds=15*60)
            lock_result.update({
                "result_code": 1,
                "result_reason": ret["message"],
                "pay_url": "",
                "raw_order_no": "",
                "expire_datetime": expire_time,
                "lock_info": ret,
            })
        else:
            if code == 2215:       # 余额不足
                pass
            lock_result.update({
                "result_code": 0,
                "result_reason": ret["message"],
                "pay_url": "",
                "raw_order_no": "",
                "expire_datetime": None,
                "lock_info": ret,
            })
        return lock_result

    def request_order_detail(self, order):
        url = config.FANGBIAN_API_URL + "/Order"
        fd = self.post_data_templ("U0202", order.order_no)
        r = requests.post(url, headers=self.post_headers(), data=urllib.urlencode(fd))
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

        ret = self.request_order_detail(order)
        if ret["code"] != 2103:
            return
        detail = ret["data"]
        state = detail["status"]

        # 3：锁票成功 14：出票成功 13：出票失败 2：正在出票
        raw_order = ""
        if state == 13:
            result_info.update({
                "result_code": 2,
                "result_msg": state,
            })
        elif state in [2, 3]:
            raw_order = detail["ticketOrderNo"]
            result_info.update({
                "result_code": 4,
                "result_msg": state,
            })
        elif state== 14:
            raw_order = detail["ticketOrderNo"]
            pick_msg = detail["pickTicketInfo"]
            result_info.update({
                "result_code": 1,
                "result_msg": state,
                "pick_code_list": ["null"],
                "pick_msg_list": [pick_msg],
            })
        if raw_order != order.raw_order_no:
            order.modify(raw_order_no=raw_order)
        return result_info

    def do_refresh_line(self, line):
        result_info = {
            "result_msg": "",
            "update_attrs": {},
        }
        line_url = config.FANGBIAN_API_URL + "/Query"
        params = {
            "departure": line.s_city_name,
            "dptCode": line.s_city_code,
            "destination": line.d_city_name,
            "desCode": line.d_city_code,
            "dptTime": line.drv_date,
            "stationCode": "",
            "queryType": "1",
            "exParms": ""
        }
        fd = self.post_data_templ("U0103", json.dumps(params))
        r = requests.post(line_url, data=urllib.urlencode(fd), headers=self.post_headers())
        res = r.json()
        now = dte.now()
        if res["code"] != 1100:
            result_info.update(result_msg="error response: %s" % res["message"],
                               update_attrs={"left_tickets": 0, "refresh_datetime": now})
            return result_info

        update_attrs = {}
        for d in res["data"]:
            dpt_time = d["dptTime"]
            lst = dpt_time.split(":")
            if len(lst) == 3:
                dpt_time = ":".join(lst[:2])
            drv_datetime = dte.strptime("%s %s" % (d["dptDate"], dpt_time), "%Y-%m-%d %H:%M")
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
            extra_info = {"exData1": d["exData1"], "exData2": d["exData2"]}
            info = {
                "full_price": float(d["ticketPrice"]),
                "fee": float(d["fee"]),
                "left_tickets": int(d["ticketLeft"] or 0),
                "refresh_datetime": now,
                "extra_info": extra_info,
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
