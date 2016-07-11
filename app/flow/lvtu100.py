#!/usr/bin/env python
# encoding: utf-8

import json
import urllib
import datetime

from app.constants import *
from app.flow.base import Flow as BaseFlow
from app.models import Lvtu100AppRebot, Line
from datetime import datetime as dte
from app.utils import md5

class Flow(BaseFlow):

    name = "lvtu100"

    def get_lock_request_info(self, order):
        rebot = order.get_lock_rebot()
        line = order.line
        riders = []
        for r in order.riders:
            riders.append({
                "idcard": r["id_number"],
                "mobile": r["telephone"],
                "passengername": r["name"],
            })
        data = {
            "ip": "192.168.3.67",
            "memberid": rebot.member_id,
            "source": "android",
            "mobile": order.contact_info["telephone"],
            "productname": "%s-%s" % (line.s_sta_name, line.d_sta_name),
            "name": order.contact_info["name"],
            "service_amount": order.ticket_amount * line.fee,
            "lstorderdetail": [
                {
                    "goods_id": str(line.extra_info["goodsid"]),
                    "listordertickets": riders,
                    "product_id": line.extra_info["productid"],
                    "productname": "%s-%s" % (line.s_sta_name, line.d_sta_name),
                    "qty": order.ticket_amount,
                    "typeid": 1
                }
            ]
        }
        return {"data": json.dumps(data, ensure_ascii=False)}

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
        url = "http://api.lvtu100.com/orders/create"
        data = rebot.post_data_templ(self.get_lock_request_info(order))
        headers = rebot.post_header()
        r = rebot.http_post(url, data=urllib.urlencode(data), headers=headers)
        res = r.json()
        if res["code"] == 0:
            expire_time = dte.now()+datetime.timedelta(seconds=20*60)
            lock_result.update({
                "result_code": 1,
                "raw_order_no": res["data"]["orderid"],
                "expire_datetime": expire_time,
            })
        else:
            lock_result.update({
                "result_code": 2,
                "result_reason": res["message"],
            })
        return lock_result

    def send_order_request(self, order):
        url = "http://api.lvtu100.com/orders/getorder"
        rebot = order.get_lock_rebot()
        data = {
            "order_id": order.raw_order_no,
            "token": rebot.token,
            "type": "administrator"
        }
        data = rebot.post_data_templ({"data": json.dumps(data)})
        headers = rebot.post_header()
        r = rebot.http_post(url, data=urllib.urlencode(data), headers=headers)
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
        if ret["code"] != 0:
            result_info.update(result_msg="状态未变化")
            return result_info
        pay_info = ret["data"]["payments"][0]
        pay_money = float(pay_info["amount"])
        pay_no = str(pay_info["payment_id"])
        if order.pay_order_no != pay_no:
            order.modify(pay_order_no=pay_no, pay_money=pay_money)
        state = ret["data"]["status"]
        if state== "出票成功":
            result_info.update({
                "result_code": 1,
                "result_msg": state,
                "pick_code_list": ret["code_list"],
                "pick_msg_list": ret["msg_list"],
            })
        elif state=="出票中":
            result_info.update({
                "result_code": 4,
                "result_msg": state,
            })
        elif state=="已取消":
            result_info.update({
                "result_code": 2,
                "result_msg": state,
            })
        elif state=="出票失败":
            result_info.update({
                "result_code": 2,
                "result_msg": state,
            })
        return result_info

    def get_pay_page(self, order, valid_code="", session=None, pay_channel="alipay" ,**kwargs):
        rebot = order.get_lock_rebot()
        is_login = rebot.test_login_status()
        if not is_login:
            is_login = (rebot.login() == "OK")

        if order.status in [STATUS_LOCK_RETRY, STATUS_WAITING_LOCK]:
            self.lock_ticket(order)

        if order.status == STATUS_WAITING_ISSUE:
            self.refresh_issue(order)
            pay_url= "http://api.lvtu100.com/cash/payment/dopay"
            data = {
                "member_id": rebot.member_id,
                "amount": 1,
                "order_id": order.raw_order_no,
                "ip": "192.168.3.67",
                "paytype_code": "malipay",
                "notify_id": 1,
                "notify_url": "api.lvtu100.com/order"
            }
            data = rebot.post_data_templ({"data": json.dumps(data)})
            headers = rebot.post_header()
            r = rebot.http_post(pay_url, data=urllib.urlencode(data), headers=headers)
            ret = r.json()
            return {"flag": "html", "content": ret["data"]}

    def do_refresh_line(self, line):
        result_info = {
            "result_msg": "",
            "update_attrs": {},
        }
        now = dte.now()
        line_url = "http://api.lvtu100.com/products/getgoods"
        rebot = Lvtu100AppRebot.get_one()
        params = {
            "startprovince": line.extra_info["startProvince"],
            "startcity": line.s_city_name,
            "departdate": line.drv_date,
            "fromstation": "",
            "pagestring": '{"page":1,"pagesize":1024}',
            "range": "",
            "stopprovince": line.extra_info["stopprovince"],
            "stopcity": line.d_city_name,
        }
        data = rebot.post_data_templ(params)
        headers = rebot.post_header()
        try:
            r = rebot.http_post(line_url, data=urllib.urlencode(data), headers=headers)
            res = r.json()
        except:
            result_info.update(result_msg="exception_ok", update_attrs={"left_tickets": 5, "refresh_datetime": now})
            return result_info

        if res["code"] != 0:
            result_info.update(result_msg="error response", update_attrs={"left_tickets": 0, "refresh_datetime": now})
            return result_info

        update_attrs = {}
        s_sta_info = {d["productid"]: d for d in res["data"]["stations"]}
        d_sta_info = {d["productid"]: d for d in res["data"]["stopstations"]}
        for d in res["data"]["flight"]["resultList"]:
            left_tickets = 10
            if int(d["islocked"]) == 1:
                left_tickets = 0
            drv_datetime=dte.strptime("%s %s" % (d["departdate"], d["departtime"]), "%Y-%m-%d %H:%M")
            s_sta = s_sta_info[d["productid"]]
            d_sta = d_sta_info[d["productid"]]
            line_id_args = {
                "s_city_name": line.s_city_name,
                "d_city_name": line.d_city_name,
                "s_sta_name": s_sta["stationname"],
                "d_sta_name": d_sta["stationname"],
                "crawl_source": line.crawl_source,
                "drv_datetime": drv_datetime,
            }
            line_id = md5("%(s_city_name)s-%(d_city_name)s-%(drv_datetime)s-%(s_sta_name)s-%(d_sta_name)s-%(crawl_source)s" % line_id_args)
            try:
                obj = Line.objects.get(line_id=line_id)
            except Line.DoesNotExist:
                continue
            extra_info = obj.extra_info
            extra_info.update({"goodsid": d["goodsid"], "itemid": d["itemid"], "productid": d["productid"]})
            info = {
                "full_price": d["price"],
                "fee": 3,
                "left_tickets": left_tickets,
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
