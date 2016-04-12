#!/usr/bin/env python
# encoding: utf-8

import random
import json
import urllib
import datetime
import urllib2
import re

from app.constants import *
from app.flow.base import Flow as BaseFlow
from app.models import Line, TzkyWebRebot
from datetime import datetime as dte
from app.utils import md5
from bs4 import BeautifulSoup


class Flow(BaseFlow):

    name = "tzky"
    BASE_URL = "http://www.tzfeilu.com:8086"

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
        with TzkyWebRebot.get_and_lock(order) as rebot:
            line = order.line
            # 未登录
            if not rebot.test_login_status():
                lock_result.update({
                    "result_code": 2,
                    "source_account": rebot.telephone,
                    "result_reason": u"账号未登录",
                })
                return lock_result

            form_url = self.BASE_URL+line.extra_info["lock_form_url"]
            cookies = json.loads(rebot.cookies)
            headers = {
                #"Content-Type": "application/x-www-form-urlencoded",
                "User-Agent": rebot.user_agent,
            }
            r = rebot.http_get(form_url, headers=headers, cookies=cookies)

            soup = BeautifulSoup(r.content, "lxml")
            # 构造表单参数
            raw_form = {}
            for obj in soup.select("#busSearchForm input"):
                name, val = obj.get("name"), obj.get("value")
                if name in ["None", "none", '']:
                    continue
                raw_form[name] = val
            raw_form["cardtype"] = "01"
            raw_for["mian"] = 0
            encode_list= [urllib.urlencode(raw_form),]
            for r in order.riders:
                d = {
                    "psgName[]": r["name"],
                    "psgIdType[]": "01",
                    "psgIdCode[]": r["id_number"],
                    "psgTel[]": rebot.telephone,
                    "psgTicketType[]": 0,
                }
                encode_list.append(urllib.urlencode(d))
            encode_str = "&".join(encode_list)
            ret = self.send_lock_request(order, rebot, encode_str)

            if ret["success"]:
                expire_time = dte.now()+datetime.timedelta(seconds=15*60)
                lock_result.update({
                    "result_code": 1,
                    "result_reason": "",
                    "raw_order_no": ret["order_no"],
                    "expire_datetime": expire_time,
                    "source_account": rebot.telephone,
                    "lock_info": ret,
                    "pay_money": ret["pay_money"],
                })
            else:
                msg = ret["msg"]
                lock_result.update({
                    "result_code": 2,
                    "result_reason": msg,
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
        submit_url = "http://www.jslw.gov.cn/busOrder.do"
        headers = {
            "User-Agent": rebot.user_agent,
            "Content-Type": "application/x-www-form-urlencoded",
        }
        cookies = json.loads(rebot.cookies)
        r = rebot.http_post(submit_url, data=data, headers=headers, cookies=cookies)
        soup = BeautifulSoup(r.content, "lxml")
        if u"系统错误提示页面" in soup.title.text:
            return {
                "success": False,
                "msg": soup.select_one(".main .error-box").text,
            }
        else:
            detail_li = soup.select(".order_detail li")
            order_no = detail_li[0].text.strip().lstrip(u"订  单 号 :").strip()
            pay_money = float(soup.select(".l_pay_m_top_l li")[1].text.strip().lstrip(u"应付金额：").rstrip(u"元").strip())
            qstr = urllib2.urlparse.urlparse(r.url).query
            url_data = {l[0]:l[1] for l in [s.split("=") for s in qstr.split("&")]}
            return {
                "success": True,
                "order_id": url_data["orderid"],
                "order_no": order_no,
                "pay_money": pay_money,
                "msg": "锁票成功",
            }

    def send_order_request(self, order):
        rebot = order.get_lock_rebot()
        detail_url = "http://www.jslw.gov.cn/busOrder.do?event=orderInfo&orderid=%s" % order.lock_info["order_id"]
        headers = {
            "User-Agent": rebot.user_agent,
        }
        cookies = json.loads(rebot.cookies)
        r = rebot.http_get(detail_url, headers=headers, cookies=cookies)
        soup = BeautifulSoup(r.content, "lxml")
        detail_li = soup.select(".order_detail li")
        # order_no = detail_li[0].text.strip().lstrip(u"订  单 号 :").strip()
        state = detail_li[1].text.strip().lstrip(u"订单状态 :").strip()
        pick_no = soup.select_one("#query_no").get('value')
        pick_code = soup.select_one("#query_random").get('value')
        seat_no = soup.select_one("#seat_no").get('value')
        left_minu = soup.select_one("#remainM")
        if left_minu:
            left_minu = int(left_minu.text)
        else:
            left_minu = 0
        return {
            "state": state,
            "pick_no": pick_no,
            "pick_code": pick_code,
            "seat_no": seat_no,
            "left_minutes": left_minu,
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
        ret = self.send_order_request(order)
        state = ret["state"]
        if state == "支付超时作废":
            result_info.update({
                "result_code": 5,
                "result_msg": state,
            })
        elif state=="购票成功":
            no, code  = ret["pick_no"], ret["pick_code"]
            dx_info = {
                "time": order.drv_datetime.strftime("%Y-%m-%d %H:%M"),
                "start": order.line.s_sta_name,
                "end": order.line.d_sta_name,
                "code": code,
                "no": no,
                "raw_order": order.raw_order_no,
            }
            dx_tmpl = DUAN_XIN_TEMPL[SOURCE_JSDLKY]
            code_list = ["%s|%s" % (no, code)]
            msg_list = [dx_tmpl % dx_info]
            result_info.update({
                "result_code": 1,
                "result_msg": state,
                "pick_code_list": code_list,
                "pick_msg_list": msg_list,
            })
        elif state == "购票中":
            result_info.update({
                "result_code": 4,
                "result_msg": state,
            })
        return result_info

    def get_pay_page(self, order, valid_code="", session=None, pay_channel="alipay" ,**kwargs):
        rebot = order.get_lock_rebot()
        is_login = rebot.test_login_status()
        if not is_login:
            rebot.login()
        if order.status in [STATUS_LOCK_RETRY, STATUS_WAITING_LOCK]:
            self.lock_ticket(order)
        if order.status == STATUS_WAITING_ISSUE:
            detail = self.send_order_request(order)
            if detail["state"] <= "已作废":
                return {"flag": "error", "content": "订单已作废"}
            #elif detail["left_minutes"] <= 0:
            #    return {"flag": "error", "content": "订单已过期"}
            pay_url = "http://www.jslw.gov.cn/bankPay.do"
            headers = {
                "User-Agent": rebot.user_agent,
                "Content-Type": "application/x-www-form-urlencoded",
            }
            params = {
                "bankId": 1402,
                "gateId1":1402,
                "orderid": order.lock_info["order_id"],
                "pay_amounts": order.pay_money,
            }
            cookies = json.loads(rebot.cookies)
            r = rebot.http_post(pay_url, data=urllib.urlencode(params), headers=headers, cookies=cookies)
            return {"flag": "html", "content": r.content}

    def do_refresh_line(self, line):
        result_info = {
            "result_msg": "",
            "update_attrs": {},
        }
        now = dte.now()
        line_url = self.BASE_URL+"/index.php/search/getBuslist"
        params = {
            "ispost": 1,
            "start_city": line.s_sta_name,
            "dd_city": line.d_city_name,
            "dd_code": line.d_city_id,
            "orderdate": line.drv_date,
        }
        rebot = TzkyWebRebot.get_one()
        headers = {
            "User-Agent": random.choice(BROWSER_USER_AGENT),
            "Content-Type": "application/x-www-form-urlencoded; charset=UTF-8",
        }
        r = rebot.http_post(line_url, headers=headers, data=urllib.urlencode(params))
        soup = BeautifulSoup(r.content.replace("<!--", "").replace("-->", ""), "lxml")
        update_attrs = {}
        for e in soup.findAll("tr"):
            lst = e.findAll("td")
            if not lst:
                continue
            # bus_num = lst[0].text.strip()
            drv_date = lst[2].text.strip()
            drv_time = lst[3].text.strip()
            price = float(lst[6].text.strip())
            left_tickets = int(lst[7].text.strip())
            lock_form_url = re.findall(r"href='(\S+)'", lst[9].select_one("a").get("onclick"))[0]
            drv_datetime = dte.strptime("%s %s" % (drv_date, drv_time), "%Y-%m-%d %H:%M")
            line_id_args = {
                "s_city_name": line.s_city_name,
                "d_city_name": line.d_city_name,
                "s_sta_name": line.s_sta_name,
                "d_sta_name": line.d_sta_name,
                "crawl_source": line.crawl_source,
                "drv_datetime": drv_datetime,
            }
            line_id = md5("%(s_city_name)s-%(d_city_name)s-%(drv_datetime)s-%(s_sta_name)s-%(d_sta_name)s-%(crawl_source)s" % line_id_args)
            try:
                obj = Line.objects.get(line_id=line_id)
            except Line.DoesNotExist:
                continue
            info = {
                "full_price": price,
                "fee": 0,
                "left_tickets": left_tickets,
                "refresh_datetime": now,
                "extra_info": {"lock_form_url": lock_form_url},
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
