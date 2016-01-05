# -*- coding:utf-8 -*-

import urllib2
import urllib
import requests
import json
import pytesseract
import cStringIO

from app.constants import *
from app.flow.base import Flow as BaseFlow
from app.models import ScqcpRebot
from datetime import datetime as dte
from PIL import Image
from lxml import etree
from tasks import issued_callback
from app import order_log


class Flow(BaseFlow):
    name = "scqcp"

    def do_lock_ticket(self, order):
        with ScqcpRebot.get_and_lock(order) as rebot:
            tickets = []
            for r in order.riders:
                lst = [r["id_number"], r["name"], r["telephone"], "0", "0"]
                tickets.append("|".join(lst))
            data = {
                "carry_sta_id": order.line.starting.station_id,
                "stop_name": order.line.extra_info["stop_name_short"],
                "str_date": "%s %s" % (order.line.drv_date, order.line.drv_time),
                "sign_id": order.line.extra_info["sign_id"],
                "phone_num": order.contact_info["telephone"],
                "buy_ticket_info": "$".join(tickets),
                "open_id": rebot.open_id,
            }
            ret = self.send_lock_request(rebot, data)
            lock_result = {
                "lock_info": ret,
                "source_account": rebot.telephone,
                "pay_money": 0,
            }
            if ret["status"] == 1:
                pay_url = "http://www.scqcp.com/ticketOrder/redirectOrder.html?pay_order_id=%s" % ret["pay_order_id"]
                total_price = 0
                for ticket in ret["ticket_list"]:
                    total_price += ticket["server_price"]
                    total_price += ticket["real_price"]
                lock_result.update({
                    "result_code": 1,
                    "result_reason": "",
                    "pay_url": pay_url,
                    "raw_order_no": ",".join(ret["web_order_id"]),
                    "expire_datetime": dte.strptime(ret["expire_time"], "%Y-%m-%d %H:%M:%S"),
                    "pay_money": total_price,
                })
            else:
                lock_result.update({
                    "result_code": 0,
                    "result_reason": ret["msg"],
                    "pay_url": "",
                    "raw_order_no": "",
                    "expire_datetime": "",
                })
            return lock_result

    def send_lock_request(self, rebot, data):
        """
        单纯向源站发锁票请求
        """
        url = urllib2.urlparse.urljoin(SCQCP_DOMAIN, "/api/v1/telecom/lock")
        request = urllib2.Request(url)
        request.add_header('User-Agent', rebot.user_agent)
        request.add_header('Authorization', rebot.token)
        request.add_header('Content-type', "application/json; charset=UTF-8")
        qstr = urllib.urlencode(data)
        response = urllib2.urlopen(request, qstr, timeout=20)
        return json.loads(response.read())

    def do_refresh_issue(self, order):
        result_info = {
            "result_code": 0,
            "result_msg": "",
            "pick_code_list": [],
            "pick_msg_list": [],
        }
        if order.status != STATUS_WAITING_ISSUE:
            result_info.update(result_msg="状态未变化")
            return result_info

        rebot = ScqcpRebot.objects.get(telephone=order.source_account)
        tickets = self.send_order_request(order, rebot)
        if not tickets:
            result_info.update(result_code=2, result_msg="已过期")
            return result_info

        status = tickets.values()[0]["order_status"]
        if status == "sell_succeeded":
            code_list, msg_list = [], []
            for tid in order.lock_info["ticket_ids"]:
                code = tickets[tid]["code"]
                if code in code_list:
                    continue
                code_list.append(code)
                dx_tmpl = DUAN_XIN_TEMPL[SOURCE_SCQCP]
                dx_info = {
                    "time": order.drv_datetime.strftime("%Y-%m-%d %H:%M"),
                    "start": order.line.starting.station_name,
                    "end": order.line.destination.station_name,
                    "amount": order.ticket_amount,
                    "code": code,
                }
                msg_list.append(dx_tmpl % dx_info)
            result_info.update({
                "result_code": 1,
                "result_msg": status,
                "pick_code_list": code_list,
                "pick_msg_list": msg_list,
            })
        elif status == "give_back_ticket":
            result_info.update({
                "result_code": 3,
                "result_msg": "源站已退票",
            })
        return result_info

    def send_order_request(self, order, rebot):
        data = {"open_id": rebot.open_id}
        uri = "/api/v1/ticket_lines/query_order"
        url = urllib2.urlparse.urljoin(SCQCP_DOMAIN, uri)
        request = urllib2.Request(url)
        request.add_header('User-Agent', rebot.user_agent)
        request.add_header('Authorization', rebot.token)
        request.add_header('Content-type', "application/json; charset=UTF-8")
        qstr = urllib.urlencode(data)
        response = urllib2.urlopen(request, qstr, timeout=20)
        ret = json.loads(response.read())

        ticket_ids = order.lock_info["ticket_ids"]
        amount = len(ticket_ids)
        data = {}
        for d in ret["ticket_list"]:
            if d["ticket_id"] in ticket_ids:
                data[d["ticket_id"]] = d
            if len(data) >= amount:
                break
        return data

    def mock_send_order_request(self, order, rebot):
        ret_info = {}
        for tid in order.lock_info["ticket_ids"]:
            ret_info[tid] = {}
            ret_info[tid]["code"] = "testqp123456"
            ret_info[tid]["order_status"] = "sell_succeeded"
        return ret_info

    def do_refresh_line(self, line):
        result_info = {
            "result_msg": "",
            "update_attrs": {},
        }
        params = dict(
            carry_sta_id=line.starting.station_id,
            stop_name=line.extra_info["stop_name_short"],
            drv_date="%s %s" % (line.drv_date, line.drv_time),
            sign_id=line.extra_info["sign_id"],
        )
        ua = random.choice(MOBILE_USER_AGENG)
        ret = ScqcpRebot.get_one().http_post("/scqcp/api/v2/ticket/query_plan_info", params, user_agent=ua)
        now = dte.now()
        if ret["status"] == 1:
            if ret["plan_info"]:
                raw = ret["plan_info"][0]
                info = {
                    "full_price": raw["full_price"],
                    "fee": raw["server_price"],
                    "left_tickets": raw["amount"],
                    "refresh_datetime": now,
                }
                result_info.update(result_msg="ok", update_attrs=info)
            else:  # 线路信息没查到
                result_info.update(result_msg="no line info", update_attrs={"left_tickets": 0, "refresh_datetime": now})
        else:
            result_info.update(result_msg="fail", update_attrs={"left_tickets": 0, "refresh_datetime": now})
        return result_info

    def get_pay_page(self, order, valid_code="", session=None, pay_channel="wy" ,**kwargs):
        headers = {
            'User-Agent': "Mozilla/5.0 (Windows NT 6.2) AppleWebKit/536.3  (KHTML, like Gecko) Chrome/19.0.1061.0 Safari/536.3",
        }
        pay_url = order.pay_url
        code = valid_code
        # 验证码处理
        if code:
            data = json.loads(session["pay_login_info"])
            code_url = data["valid_url"]
            headers = data["headers"]
            cookies = data["cookies"]
            token = data["token"]
        else:
            login_form_url = "http://scqcp.com/login/index.html"
            r = requests.get(login_form_url, headers=headers)
            sel = etree.HTML(r.content)
            cookies = dict(r.cookies)
            code_url = sel.xpath("//img[@id='txt_check_code']/@src")[0]
            token = sel.xpath("//input[@id='csrfmiddlewaretoken1']/@value")[0]
            r = requests.get(code_url, headers=headers, cookies=cookies)
            cookies.update(dict(r.cookies))
            tmpIm = cStringIO.StringIO(r.content)
            im = Image.open(tmpIm)
            code = pytesseract.image_to_string(im)

        accounts = SOURCE_INFO[SOURCE_SCQCP]["accounts"]
        passwd, _ = accounts[order.source_account]
        data = {
            "uname": order.source_account,
            "passwd": passwd,
            "code": code,
            "token": token,
        }
        r = requests.post("http://scqcp.com/login/check.json", data=data, headers=headers, cookies=cookies)
        cookies.update(dict(r.cookies))
        ret = r.json()
        if ret["success"]:
            r = requests.get(pay_url, headers=headers, cookies=cookies)
            r_url = urllib2.urlparse.urlparse(r.url)
            if r_url.path in ["/error.html", "/error.htm"]:
                order.modify(status=STATUS_ISSUE_FAIL)
                order.on_issue_fail(reason="get error page when pay")
                order_log.info("[issue-refresh-result] %s fail. get error page.", order.order_no)
                issued_callback.delay(order.order_no)
                return {"flag": "html", "content": r.content}
            sel = etree.HTML(r.content)
            plateform = pay_channel
            data = dict(
                payid=sel.xpath("//input[@name='payid']/@value")[0],
                bank=sel.xpath("//input[@id='s_bank']/@value")[0],
                plate=sel.xpath("//input[@id='s_plate']/@value")[0],
                plateform=plateform,
                qr_pay_mode=0,
                discountCode=sel.xpath("//input[@id='discountCode']/@value")[0]
            )

            info_url = "http://scqcp.com:80/ticketOrder/middlePay.html"
            r = requests.post(info_url, data=data, headers=headers, cookies=cookies)
            return {"flag": "html", "content": r.content}
        elif ret["msg"] == "验证码不正确":
            data = {
                "cookies": cookies,
                "headers": headers,
                "valid_url": code_url,
                "token": token,
            }
            session["pay_login_info"] = json.dumps(data)
            return {"flag": "input_code", "content": ""}
