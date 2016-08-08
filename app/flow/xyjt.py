# coding=utf-8

import requests
import urllib
import datetime
import random
import urlparse
import re

from app.constants import *
from bs4 import BeautifulSoup as bs
from datetime import datetime as dte
from app.flow.base import Flow as BaseFlow
from app.models import Line, XyjtWebRebot
from app.utils import md5, get_redis
from app import rebot_log


class Flow(BaseFlow):
    name = 'xyjt'

    # 锁票
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
        base_url = "http://order.xuyunjt.com"
        rebot = order.get_lock_rebot()
        line = order.line
        line.refresh()

        # 进入表单页
        headers = {
            'User-Agent': random.choice(BROWSER_USER_AGENT)
        }
        cookies = {}
        lock_url = urlparse.urljoin(base_url, line.extra_info["lock_url"])
        r = rebot.http_get(lock_url, headers=headers)
        cookies.update(dict(r.cookies))

        # 提交参数
        soup = bs(r.content, "lxml")
        lock_url = urlparse.urljoin(base_url, soup.select_one("#aspnetForm").get('action'))
        lock_url = lock_url.replace("%u", "\u")
        params = {}
        for o in soup.select("#aspnetForm input"):
            params[o.get("name")] = o.get("value")
        params ={
            "__EVENTVALIDATION": params["__EVENTVALIDATION"],
            "__VIEWSTATE": params["__VIEWSTATE"],
            "__EVENTTARGET": params["__EVENTTARGET"],
            "__EVENTARGUMENT": params["__EVENTARGUMENT"],
            "ctl00$ContentPlaceHolder1$txtjp_price": params["ctl00$ContentPlaceHolder1$txtjp_price"],
            "ctl00$ContentPlaceHolder1$txttp_price": params["ctl00$ContentPlaceHolder1$txttp_price"],
            "ctl00$ContentPlaceHolder1$txtqp_price": params["ctl00$ContentPlaceHolder1$txtqp_price"],
            "ctl00$ContentPlaceHolder1$txtoffer_price": 0,
            "ctl00$ContentPlaceHolder1$ddlqp": order.ticket_amount,
            "ctl00$ContentPlaceHolder1$ddljp": 0,
            "ctl00$ContentPlaceHolder1$ddltp": 0,
            "ctl00$ContentPlaceHolder1$txttotal": order.ticket_amount,
            "ctl00$ContentPlaceHolder1$txttotalprice": order.ticket_amount * float(params["ctl00$ContentPlaceHolder1$txtqp_price"]),
            "ctl00$ContentPlaceHolder1$txtcardno": order.contact_info["id_number"],
            "ctl00$ContentPlaceHolder1$Imgbtnsubmit.x":54,
            "ctl00$ContentPlaceHolder1$Imgbtnsubmit.y":20,
        }
        headers = {
            'User-Agent': random.choice(BROWSER_USER_AGENT),
            "Content-Type": "application/x-www-form-urlencoded",
        }
        r = rebot.http_post(lock_url, data=urllib.urlencode(params), cookies=cookies, headers=headers)
        cookies.update(dict(r.cookies))
        soup = bs(r.content, "lxml")

        # 下单锁票
        lock_url = urlparse.urljoin(base_url, soup.select_one("#netordersubmit").get('action'))
        params = {}
        for o in soup.select("#netordersubmit input"):
            params[o.get("name")] = o.get("value")
        r = rebot.http_post(lock_url, data=urllib.urlencode(params), cookies=cookies, headers=headers)
        cookies.update(dict(r.cookies))
        soup = bs(r.content, "lxml")

        # 下单锁票2
        lock_url = urlparse.urljoin(base_url, soup.select_one("#aspnetForm").get('action'))
        params = {}
        for o in soup.select("#aspnetForm input"):
            params[o.get("name")] = o.get("value")
        params = {
            "__VIEWSTATE": params["__VIEWSTATE"],
            "__EVENTVALIDATION": params["__EVENTVALIDATION"],
            "ctl00$ContentPlaceHolder1$hdfincountry": params["ctl00$ContentPlaceHolder1$hdfincountry"],
            "ctl00$ContentPlaceHolder1$hdfselectedseat": params["ctl00$ContentPlaceHolder1$hdfselectedseat"],
            "ctl00$ContentPlaceHolder1$alipaygroup": "RBtnAlipay",
            "ctl00$ContentPlaceHolder1$Imgbtnsubmit.x": 24,
            "ctl00$ContentPlaceHolder1$Imgbtnsubmit.y": 8,
            "ctl00$ContentPlaceHolder1$TxtSubject": "徐运集团--长途汽车票",
            "ctl00$ContentPlaceHolder1$TxtBody": "",
        }
        r = rebot.http_post(lock_url, data=urllib.urlencode(params), cookies=cookies, headers=headers)
        cookies.update(dict(r.cookies))
        soup = bs(r.content, "lxml")

        # 支付页面
        params = {}
        for o in soup.select("#netchecksubmit input"):
            params[o.get("name")] = o.get("value")
        raw_order = params["bespoke_id"]
        lock_url = urlparse.urljoin(base_url, soup.select_one("#netchecksubmit").get('action'))
        headers.update({
            "Origin": "http://order.xuyunjt.com",
            "Referer": "http://order.xuyunjt.com/wsdgnetcheck.aspx",
        })
        r = rebot.http_post(lock_url, data=urllib.urlencode(params), cookies=cookies, headers=headers)
        cookies.update(dict(r.cookies))
        soup = bs(r.content, "lxml")

        # 支付页面2
        lock_url = urlparse.urljoin(base_url, soup.select_one("#aspnetForm").get('action'))
        params = {}
        for o in soup.select("#aspnetForm input"):
            params[o.get("name")] = o.get("value")
        params["ctl00$ContentPlaceHolder1$Imgbtnsubmit2.x"] = 72
        params["ctl00$ContentPlaceHolder1$Imgbtnsubmit2.y"] = 27
        r = rebot.http_post(lock_url, data=urllib.urlencode(params), cookies=cookies, headers=headers)
        cookies.update(dict(r.cookies))
        pay_url = re.findall(r"window.open\(\'(\S+)',''", r.content)[0]

        if raw_order:
            expire_time = dte.now() + datetime.timedelta(seconds=15 * 60)
            lock_result.update({
                'result_code': 1,
                'raw_order_no': raw_order,
                "expire_datetime": expire_time,
                "source_account": rebot.telephone,
                'pay_money': float(re.findall(r"total_fee=(\S+)&sign=", pay_url)[0]),
                "pay_url": pay_url,
                "lock_info": {},
            })
            return lock_result
        else:
            lock_result.update({
                "source_account": rebot.telephone,
                'result_code': 2,
                "lock_info": {"fail_reason": soup.title.get_text()}
            })
            return lock_result

    def send_order_request(self, order):
        rebot = order.get_lock_rebot()
        sn = order.pay_order_no
        url = 'http://order.xuyunjt.com/wsdgalipayddcx.aspx'
        headers = {
            "User-Agent": rebot.user_agent,
        }
        headers['Content-Type'] = 'application/x-www-form-urlencoded'
        r = requests.get(url, headers=headers)
        soup = bs(r.content, 'lxml')
        state = soup.find(
            'input', attrs={'name': '__VIEWSTATE', 'id': '__VIEWSTATE'}).get('value', '')
        validation = soup.find('input', attrs={
            'name': '__EVENTVALIDATION', 'id': '__EVENTVALIDATION'}).get('value', '')
        data = {
            '__EVENTTARGET': '',
            '__EVENTARGUMENT': '',
            '__LASTFOCUS': '',
            '__VIEWSTATE': state,
            '__EVENTVALIDATION': validation,
            'ctl00$ContentPlaceHolder1$txtbespoke_id': order.raw_order_no,
            'ctl00$ContentPlaceHolder1$txtcardno': order.contact_info.get('id_number'),
            'ctl00$ContentPlaceHolder1$ddlcond': '全部',
            'ctl00$ContentPlaceHolder1$ImageButton1.x': '23',
            'ctl00$ContentPlaceHolder1$ImageButton1.y': '18',
        }
        r = requests.post(url, headers=headers,
                          cookies=r.cookies, data=urllib.urlencode(data))
        soup = bs(r.content, 'lxml')
        try:
            info = soup.find('table', attrs={'id': 'ctl00_ContentPlaceHolder1_GridView1'}).find_all(
                'tr', attrs={'class': 'GridViewRowStyle'})
            for x in info:
                sn1 = x.find('input', attrs={
                             'id': 'ctl00_ContentPlaceHolder1_GridView1_ctl02_hdfbespoke_id'}).get('value', '').strip()
                rebot_log.info(sn1)
                if sn == sn1:
                    state = x.find('span', attrs={
                                   'id': 'ctl00_ContentPlaceHolder1_GridView1_ctl02_lblticketstatus'}).get_text()
                    pcode = x.find('span', attrs={
                                   'id': 'ctl00_ContentPlaceHolder1_GridView1_ctl02_lblget_ticket_passwd'}).get_text().strip()
                    return {
                        "state": state,
                        "pick_no": pcode,
                        "pick_code": pcode,
                        "pick_site": '',
                        'raw_order': sn,
                        "pay_money": 0.0,
                    }
        except:
            pass

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
        code = ret['pick_code']
        if '已取消' in state:
            result_info.update({
                "result_code": 5,
                "result_msg": state,
            })
        elif '已购' in state:
            no, site, raw_order = ret['pick_no'], ret[
                'pick_site'], ret['raw_order']
            dx_info = {
                "time": order.drv_datetime.strftime("%Y-%m-%d %H:%M"),
                "start": order.line.s_sta_name,
                "end": order.line.d_sta_name,
                "code": code,
                "no": no,
                "site": site,
                'raw_order': raw_order,
                'buscode': order.line.bus_num,
            }
            dx_tmpl = DUAN_XIN_TEMPL[SOURCE_XYJT]
            code_list = ["%s" % (code)]
            msg_list = [dx_tmpl % dx_info]
            result_info.update({
                "result_code": 1,
                "result_msg": state,
                "pick_code_list": code_list,
                "pick_msg_list": msg_list,
            })
        return result_info

    def do_refresh_line(self, line):
        result_info = {
            "result_msg": "",
            "update_attrs": {},
        }
        rebot = XyjtWebRebot.get_one()
        url = 'http://order.xuyunjt.com/wsdgbccx.aspx'
        rds = get_redis("line")
        vs_key = "xyjt:viewstate:%s" % line.s_sta_id
        vs = rds.get(vs_key) or ""
        now = dte.now()
        headers = {
            "User-Agent": random.choice(BROWSER_USER_AGENT),
            "Content-Type": "application/x-www-form-urlencoded"
        }

        if not vs:
            # VIEWSTATE 各个站都不一样
            try:
                r = rebot.http_get("http://order.xuyunjt.com/wsdgbccx.aspx", headers=headers)
                soup = bs(r.content, "lxml")
                vs = soup.select_one("#__VIEWSTATE").get("value")
                data = {
                    'ctl00$ContentPlaceHolder1$ScriptManager1': 'ctl00$ContentPlaceHolder1$ScriptManager1|ctl00$ContentPlaceHolder1$BtnBccx',
                    '__EVENTARGUMENT': '',
                    '__LASTFOCUS': '',
                    '__VIEWSTATE': vs,
                    'ctl00$ContentPlaceHolder1$ddlincounty': line.s_sta_id,
                    'ctl00$ContentPlaceHolder1$ddlsaledate': line.drv_datetime.strftime("%Y%m%d"),
                    'ctl00$ContentPlaceHolder1$txtstop': u"南京",
                    'radio': u"南京",
                }
                r = rebot.http_post(url, headers=headers, data=urllib.urlencode(data))
                soup = bs(r.content, 'lxml')
            except:
                result_info.update(result_msg="exception_ok_vserror", update_attrs={"left_tickets": 5, "refresh_datetime": now})
                return result_info
            vs = soup.select_one("#__VIEWSTATE").get("value")
            rds.set(vs_key, vs)
            rds.expire(vs_key, 30*60*60)

        data = {
            'ctl00$ContentPlaceHolder1$ScriptManager1': 'ctl00$ContentPlaceHolder1$ScriptManager1|ctl00$ContentPlaceHolder1$BtnBccx',
            'ctl00$ContentPlaceHolder1$BtnBccx': '班次查询',
            '__EVENTARGUMENT': '',
            '__LASTFOCUS': '',
            '__VIEWSTATE': vs,
            'ctl00$ContentPlaceHolder1$ddlincounty': line.s_sta_id,
            'ctl00$ContentPlaceHolder1$ddlsaledate': line.drv_datetime.strftime("%Y%m%d"),
            'ctl00$ContentPlaceHolder1$txtstop': line.d_city_name,
            'radio': "",
        }
        try:
            r = rebot.http_post(url, headers=headers, data=urllib.urlencode(data))
            soup = bs(r.content, 'lxml')
        except:
            result_info.update(result_msg="exception_ok", update_attrs={"left_tickets": 5, "refresh_datetime": now})
            return result_info

        update_attrs = {}
        db_lines = {x.line_id: x for x in Line.objects.filter(s_city_name=line.s_city_name,d_city_name=line.d_city_name, drv_date=line.drv_date)}
        for tr_o in soup.select("#ctl00_ContentPlaceHolder1_GVBccx tr")[1:]:
            if tr_o.get("class") and "GridViewHeaderStyle" in tr_o.get("class"):
                continue
            td_lst = tr_o.select("td")
            index_tr = lambda idx: td_lst[idx].text.strip()
            drv_date, drv_time = index_tr(0), index_tr(5)
            if u"流水" in drv_time:
                continue
            drv_datetime=dte.strptime("%s %s" % (drv_date, drv_time), "%Y-%m-%d %H:%M")
            left_tickets=int(index_tr(8))
            full_price=float(index_tr(6))

            line_id_args = {
                "s_city_name": line.s_city_name,
                "d_city_name": line.d_city_name,
                "s_sta_name": unicode(index_tr(1)),
                "d_sta_name": unicode(index_tr(3)),
                "crawl_source": line.crawl_source,
                "drv_datetime": drv_datetime,
            }
            attrs = {
                "left_tickets": left_tickets,
                "refresh_datetime": now,
                "full_price": full_price,
                "extra_info__lock_url": td_lst[12].find("a").get("href"),
            }
            line_id = md5("%(s_city_name)s-%(d_city_name)s-%(drv_datetime)s-%(s_sta_name)s-%(d_sta_name)s-%(crawl_source)s" % line_id_args)
            if line_id in db_lines:
                db_lines[line_id].update(**attrs)
            if line_id == line.line_id:
                update_attrs = attrs
        if not update_attrs:
            result_info.update(result_msg="no line info", update_attrs={"left_tickets": 0, "refresh_datetime": now})
        else:
            result_info.update(result_msg="ok", update_attrs=update_attrs)
        return result_info

    def get_pay_page(self, order, valid_code="", session=None, pay_channel="alipay", **kwargs):
        # 获取alipay付款界面
        if order.status in [STATUS_LOCK_RETRY, STATUS_WAITING_LOCK]:
            self.lock_ticket(order)

        if order.status == STATUS_WAITING_ISSUE:
            pay_url = order.pay_url
            no, pay = "", 0
            for s in pay_url.split("?")[1].split("&"):
                k, v = s.split("=")
                if k == "out_trade_no":
                    no = v
                elif k == "total_fee":
                    pay = float(v)
            if no and order.pay_order_no != no:
                order.modify(pay_order_no=no, pay_money=pay,pay_channel='alipay')
            return {"flag": "url", "content": pay_url}
        return "锁票失败, 请重试"
