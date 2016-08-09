#!/usr/bin/env python
# encoding: utf-8

import random
import json
import urllib
import datetime
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
        raw_form["mian"] = 0
        raw_form["bxFlag"] = 0      # 保险
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

        submit_url = soup.select_one("#busSearchForm").get("action")
        headers["Content-Type"] = "application/x-www-form-urlencoded"
        r = rebot.http_post(submit_url, headers=headers, cookies=cookies, data=encode_str)
        if u"busOrder/zhifu" in r.url:
            expire_time = dte.now()+datetime.timedelta(seconds=15*60)
            lock_info = {"detail_url": r.url}
            lock_result.update({
                "result_code": 1,
                "result_reason": "",
                "expire_datetime": expire_time,
                "source_account": rebot.telephone,
                "lock_info": lock_info,
            })
        else:
            lock_result.update({
                "result_code": 0,
                "result_reason": u"不明原因:"+r.url,
                "source_account": rebot.telephone,
            })
        return lock_result

    def send_order_request(self, order):
        rebot = order.get_lock_rebot()
        issue_url = self.BASE_URL + "/index.php/busorder/has_ticket"
        today = dte.now().strftime("%Y-%m-%d")
        params = {
            "ispost": 1,
            "type": 1,
            "startdate": today,
            "enddate": today,
        }
        cookies = json.loads(rebot.cookies)
        headers = {
            "Content-Type": "application/x-www-form-urlencoded",
            "User-Agent": rebot.user_agent,
        }
        r = rebot.http_post(issue_url, headers=headers, cookies=cookies, data=urllib.urlencode(params))
        soup = BeautifulSoup(r.content, "lxml")
        if order.raw_order_no:
            tag_obj = soup.find(href=re.compile(r"tiket/index/%s" % order.raw_order_no))
            if tag_obj:
                td_lst = tag_obj.parent.parent.find_all("td")
                pick_no = td_lst[7].text
                pick_code  = td_lst[8].text
                state = td_lst[9].text
                money = float(td_lst[6].text)
                if money != order.pay_money:
                    raise Exception()
                if state == "有效":
                    return {
                        "state": "购票成功",
                        "pick_no": pick_no,
                        "pick_code": pick_code,
                    }
                else:
                    # 暂时抛异常, 遇到之后再处理
                    raise Exception()

        detail_url = order.lock_info["detail_url"]
        headers = {"User-Agent": rebot.user_agent}
        r = rebot.http_get(detail_url, headers=headers, cookies=cookies)
        if "订单已过期" in r.content:
            state = "已过期"
            return {"state": state,}
        else:
            soup = BeautifulSoup(r.content, "lxml")
            detail_li = soup.select(".order_detail li")
            order_no = detail_li[0].text.strip().lstrip(u"订  单 号 :").strip()
            state = detail_li[1].text.strip().lstrip(u"订单状态 :").strip()
            subject = soup.find("input", attrs={"name": "subject"}).get("value")
            pay_money = float(soup.select(".l_pay_m_top_l li")[1].text.strip().lstrip(u"应付金额：").rstrip(u"元").strip())
            return {
                "state": state,
                "pick_no": "",
                "pick_code": "",
                "seat_no": "",
                "subject": subject,
                "order_no": order_no,
                "pay_money": pay_money,
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
        if ret.get("order_no", "") and order.raw_order_no != ret["order_no"]:
            lock_info = order.lock_info
            lock_info["subject"] = ret["subject"]
            order.modify(raw_order_no=ret["order_no"], lock_info=lock_info, pay_money=ret["pay_money"])

        state = ret["state"]
        if state == "已过期":  # 付款了也可能变成已过期状态, 从而造成重复下单支付
            pass
            # result_info.update({
            #     "result_code": 5,
            #     "result_msg": state,
            # })
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
            dx_tmpl = DUAN_XIN_TEMPL[SOURCE_TZKY]
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
            self.refresh_issue(order)
            order.reload()
            pay_url = "http://www.tzfeilu.com:8086/index.php/blank"
            headers = {
                "User-Agent": rebot.user_agent,
                "Content-Type": "application/x-www-form-urlencoded",
            }
            params={
                "bankId": 1402,
                "gateId": 1010,
                "gateId1": "ali",
                "gateId5": "upop",
                "gateId6": "kjzh",
                "orderid": order.raw_order_no,
                "pay_amounts": order.pay_money,
                "subject": order.lock_info["subject"],
            }
            cookies = json.loads(rebot.cookies)
            r = rebot.http_post(pay_url, data=urllib.urlencode(params), headers=headers, cookies=cookies)
            order.update(pay_channel='alipay')
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
        try:
            r = rebot.http_post(line_url, headers=headers, data=urllib.urlencode(params))
        except:
            result_info.update(result_msg="exception_ok", update_attrs={"left_tickets": 2, "refresh_datetime": now})
            return result_info
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
