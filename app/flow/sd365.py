# coding=utf-8

import re
import urllib
import datetime
import random

from bs4 import BeautifulSoup
from app.constants import *
from datetime import datetime as dte
from app.flow.base import Flow as BaseFlow
from app.models import Sd365WebRebot, AdminUser


class Flow(BaseFlow):
    name = 'sd365'

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
        line = order.line

        # confirm
        headers = {'User-Agent': random.choice(BROWSER_USER_AGENT)}
        params = {
            "c": "tkt3",
            "a": "confirm",
            "sid": line.extra_info["sid"],
            "l": line.extra_info["l"],
            "dpid": line.extra_info["dpid"],
            "t": line.drv_date,
        }
        rebot.modify(ip="")
        r = rebot.http_get("http://www.365tkt.com/?"+ urllib.urlencode(params), headers=headers)
        cookies = r.cookies
        soup = BeautifulSoup(r.content, "lxml")
        params = {unicode(o.get("name")): unicode(o.get("value")) for o in soup.select("#orderlistform input")}
        if not params:
            if r.status_code == 200 and not r.content:
                self.close_line(line, reason="响应内容为空")
                lock_result.update({
                    "result_code": 0,
                    "source_account": rebot.telephone,
                    "result_reason": "响应内容为空",
                })
                return lock_result
            errmsg = soup.select_one(".jump_mes h4").text
            if u"该班次价格不存在" in errmsg or u"发车前2小时不售票" in errmsg or u"超出人数限制" in errmsg:
                self.close_line(line, reason=errmsg)
                lock_result.update({
                    "result_code": 0,
                    "source_account": rebot.telephone,
                    "result_reason": errmsg,
                })
                return lock_result
            else:
                lock_result.update({
                    "result_code": 2,
                    "source_account": rebot.telephone,
                    "result_reason": errmsg,
                })
                return lock_result

        # confirming
        pick_code = random.randint(111111, 999999)
        params2 = {
            "savefriend[]": [0 for i in range(len(order.riders))],
            "tktname[]": [d["name"] for d in order.riders],
            "papertype[]": [0 for i in range(len(order.riders))],
            "paperno[]": [d["id_number"] for d in order.riders],
            "offertype[]": [1 for i in range(len(order.riders))],
            "price[]": [line.full_price for i in range(len(order.riders))],
            "insureproduct[]": [1 for i in range(len(order.riders))],
            "insurenum[]": [0 for i in range(len(order.riders))],
            "insurefee[]": [0 for i in range(len(order.riders))],
            "chargefee[]": [0 for i in range(len(order.riders))],
            "member_name": order.contact_info["name"],
            "tktphone": order.contact_info["telephone"],
            "ticketpass": pick_code,
        }
        params.update(params2)
        headers.update({
            "Content-Type": "application/x-www-form-urlencoded",
        })
        url = "http://www.365tkt.com/?c=tkt3&a=confirming"
        r = rebot.http_post(url, headers=headers, cookies=cookies, data=urllib.urlencode(params, doseq=1))
        cookies = cookies.update(r.cookies)

        # lock
        soup = BeautifulSoup(r.content, "lxml")
        params = {}
        for o in soup.select("#tktlock input"):
            name, value = unicode(o.get("name") or ""), unicode(o.get("value") or "")
            if not name:
                continue
            if name.endswith("[]"):
                params.setdefault(name, []).append(value)
            else:
                params[name]=value

        kefu = AdminUser.objects.get(username=order.kefu_username)
        # params["bankname"] = "ZHIFUBAO"  # 支付宝支付
        # params["paytype"] = "3"  # 支付宝支付
        params["paytype"] = "1"  # 支付宝支付
        params["bankname"] = kefu.yh_type
        params["member_name"] = order.contact_info["name"]

        url = 'http://www.36565.cn/?c=tkt3&a=payt'
        headers.update({
            "Referer": "http://www.365tkt.com/?c=tkt3&a=confirming",
        })
        r = rebot.http_post(url, headers=headers, data=urllib.urlencode(params, doseq=1), allow_redirects=False, timeout=30, cookies=cookies)
        location = urllib.unquote(r.headers.get('location', ''))
        if 'mapi.alipay.com' in location:
            sn = location.split(',')[3]
            expire_time = dte.now() + datetime.timedelta(seconds=15 * 60)
            order.modify(extra_info={'pay_url': location, 'sn': sn, 'pcode': pick_code})
            lock_result.update({
                'result_code': 1,
                'raw_order_no': sn,
                "expire_datetime": expire_time,
                "source_account": rebot.telephone,
                'pay_money': 0,
                "result_reason": location,
            })
            return lock_result
        else:
            code = 2
            if "检票车站在班次途经站中不存在" in location:
                self.close_line(line, reason=location)
                code = 0
            lock_result.update({
                'result_code': code,
                "result_reason": location,
                "source_account": rebot.telephone,
            })
            return lock_result

    def send_order_request(self, order):
        ua = random.choice(BROWSER_USER_AGENT)
        headers = {'User-Agent': ua}
        headers['Content-Type'] = 'application/x-www-form-urlencoded'
        url = 'http://www.36565.cn/?c=order2&a=index'
        rebot = order.get_lock_rebot()
        rebot.modify(ip="")
        for y in order.riders:
            data = {'eport': y['id_number']}
            try:
                r = rebot.http_post(url, headers=headers, data=data)
                soup = BeautifulSoup(r.content, 'lxml')
                info = soup.find_all('div', attrs={'class': 'userinfoff'})[1].find_all('div', attrs={'class': 'billinfo'})
            except Exception,e:
                return {
                    "state": 'proxy error',
                    "pick_no": '',
                    "pcode": order.extra_info.get('pcode'),
                    "pick_site": '',
                    'raw_order': order.extra_info.get('orderUUID'),
                    "pay_money": 0.0,
                    'amount': '',
                }
            sn = order.pay_order_no
            for x in info:
                sn1 = x.find('div', attrs={'class': 'billnobreak'}).get_text().strip()
                state = x.find('div', attrs={'class': 'bstate'}).get_text().strip()
                amount = int(x.find('div', attrs={'class': 'busnum'}).get_text().strip())
                if sn1 == sn:
                    return {
                        "state": state,
                        "pick_no": '',
                        "pcode": order.extra_info.get('pcode'),
                        "pick_site": '',
                        'raw_order': order.extra_info.get('orderUUID'),
                        "pay_money": 0.0,
                        'amount': amount,
                    }

    # 刷新出票
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
        state = ret['state']
        if '失败' in state:
            result_info.update({
                "result_code": 2,
                "result_msg": state,
            })
        elif '购票成功' in state:
            amount, pcode = ret['amount'], ret['pcode']
            dx_info = {
                "time": order.drv_datetime.strftime("%Y-%m-%d %H:%M"),
                "start": order.line.s_sta_name,
                "end": order.line.d_sta_name,
                "pcode": pcode,
                'amount': amount,
            }
            dx_tmpl = DUAN_XIN_TEMPL[SOURCE_SD365]
            code_list = ["%s" % (pcode)]
            msg_list = [dx_tmpl % dx_info]
            result_info.update({
                "result_code": 1,
                "result_msg": state,
                "pick_code_list": code_list,
                "pick_msg_list": msg_list,
            })
        return result_info

    def do_refresh_line(self, line):
        result_info = {}
        now = dte.now()
        headers = {
            "User-Agent": random.choice(BROWSER_USER_AGENT),
            "Referer": "http://www.365tkt.com/",
        }
        rebot = Sd365WebRebot.get_one()
        headers = {'User-Agent': random.choice(BROWSER_USER_AGENT)}
        params = {
            "c": "tkt3",
            "a": "confirm",
            "sid": line.extra_info["sid"],
            "l": line.extra_info["l"],
            "dpid": line.extra_info["dpid"],
            "t": line.drv_date,
        }
        rebot.modify(ip="")
        try:
            r = rebot.http_get("http://www.365tkt.com/?"+ urllib.urlencode(params), headers=headers)
        except:
            result_info.update(result_msg="net_error", update_attrs={"left_tickets": 5, "refresh_datetime": now})
            return result_info

        soup = BeautifulSoup(r.content, "lxml")
        params = {unicode(o.get("name")): unicode(o.get("value")) for o in soup.select("#orderlistform input")}
        if not params:
            if r.status_code == 200 and not r.content:
                result_info.update(result_msg="响应内容为空", update_attrs={"left_tickets": 0, "refresh_datetime": now})
                return result_info
            errmsg = soup.select_one(".jump_mes h4")
            if errmsg:
                errmsg = errmsg.text
                result_info.update(result_msg=errmsg, update_attrs={"left_tickets": 0, "refresh_datetime": now})
            else:
                result_info.update(result_msg="exception_ok1", update_attrs={"left_tickets": 5, "refresh_datetime": now})
        else:
            try:
                left_tickets = int(soup.select_one("#leftnum").text)
                full_price = float(soup.select(".tktdata div")[3].text.strip().lstrip(u"￥").strip())
                result_info.update(result_msg="ok", update_attrs={"left_tickets": left_tickets, "refresh_datetime": now, "full_price": full_price})
            except:
                result_info.update(result_msg="exception_ok2", update_attrs={"left_tickets": 5, "refresh_datetime": now})
        return result_info

    def get_pay_page(self, order, valid_code="", session=None, **kwargs):

        # 获取alipay付款界面
        def _get_page():
            if order.status == STATUS_WAITING_ISSUE:
                pay_url = order.extra_info.get('pay_url')
                no, pay = "", 0
                for s in pay_url.split("?")[1].split("&"):
                    k, v = s.split("=")
                    if k == "out_trade_no":
                        no = v
                    elif k == "total_fee":
                        pay = float(v)
                if no and order.pay_order_no != no:
                    order.modify(pay_order_no=no, pay_money=pay, pay_channel='yh')
                return {"flag": "url", "content": pay_url}
        if order.status in [STATUS_LOCK_RETRY, STATUS_WAITING_LOCK]:
            self.lock_ticket(order)
        order.reload()
        if order.status == STATUS_WAITING_ISSUE:
            return _get_page()
