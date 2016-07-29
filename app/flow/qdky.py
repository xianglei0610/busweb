# coding=utf-8

import requests
import re
import time
import json
import urllib

import datetime
import random
from bs4 import BeautifulSoup as bs
# from PIL import Image

from app.constants import *
from datetime import datetime as dte
from app.flow.base import Flow as BaseFlow
from app.models import Line
from app.utils import md5
from app import rebot_log
# import cStringIO
from time import sleep


class Flow(BaseFlow):
    name = 'qdky'

    def update_state(self):
        url = 'http://www.qdjyjt.com/infor/select1.aspx'
        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 6.1; WOW64; rv:47.0) Gecko/20100101 Firefox/47.0",
            'Content-Type': 'application/x-www-form-urlencoded',
        }
        for x in xrange(5):
            r = requests.get(url, headers=headers)
            soup = bs(r.content, 'lxml')
            try:
                state = soup.find('input', attrs={'id': '__VIEWSTATE'}).get('value', '')
                valid = soup.find('input', attrs={'id': '__EVENTVALIDATION'}).get('value', '')
                if state and valid and r.ok:
                    return (state, valid, dict(r.cookies))
            except:
                pass
    # 锁票
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
        if not valid_code:
            lock_result.update({
                'result_code': 2,
                "lock_info": {"fail_reason": "input_code"}
            })
            return lock_result
        rebot = order.get_lock_rebot()
        v = rebot.add_riders(order)
        if v[0] == '2332':
            lock_result.update({
                'result_code': 0,
                'result_reason': v[1],
            })
            return lock_result
        if v[0] == '2333':
            lock_result.update({
                'result_code': 2,
                'result_reason': v[1],
            })
            return lock_result
        pk = len(order.riders)
        tpass = random.randint(111111, 999999)
        data = {
            '__EVENTTARGET': '',
            '__EVENTARGUMENT': '',
            '__VIEWSTATE': v[1],
            '__EVENTVALIDATION': v[2],
            'ctl00$ContentPlaceHolder1$DropDownList1': pk,
            'MyRadioButton': v[0],
            'ctl00$ContentPlaceHolder1$GridView1$ctl%s$txtpwd' %(str(int(v[0])+2).zfill(2)): str(tpass),
            'ctl00$ContentPlaceHolder1$checktxt2': valid_code,
            'ctl00$ContentPlaceHolder1$show': u'提交订单',
        }
        url = 'http://ticket.qdjyjt.com/'
        cookies = json.loads(rebot.cookies)
        headers = {
            'User-Agent': rebot.user_agent,
            'Content-Type': 'application/x-www-form-urlencoded',
        }
        r = rebot.http_post(url, headers=headers,cookies=cookies, data=data, timeout=128)
        soup = bs(r.content, 'lxml')
        state = soup.find('input', attrs={'id': '__VIEWSTATE'}).get('value', '')
        valid = soup.find('input', attrs={'id': '__EVENTVALIDATION'}).get('value', '')
        data = {}
        data = {
            '__EVENTTARGET': '',
            '__EVENTARGUMENT': '',
            '__VIEWSTATE': state,
            '__EVENTVALIDATION': valid,
            'ctl00$ContentPlaceHolder1$DropDownList1': str(pk),
            'ctl00$ContentPlaceHolder1$checktxt2': valid_code,
            'ctl00$ContentPlaceHolder1$collectPersonViewSubmitButton': u'确定',
        }
        headers['Referer'] = 'http://ticket.qdjyjt.com/'
        headers['Host'] = 'ticket.qdjyjt.com'
        r = rebot.http_post(url, headers=headers,cookies=cookies, data=urllib.urlencode(data), timeout=128)
        soup = bs(r.content, 'lxml')
        try:
            state = soup.find('input', attrs={'id': '__VIEWSTATE'}).get('value', '')
            valid = soup.find('input', attrs={'id': '__EVENTVALIDATION'}).get('value', '')
        except:
            lock_result.update({
                'result_code': 2,
                "result_reason": '验证码错误',
            })
            return lock_result
        data = {}
        data = {
            '__EVENTTARGET': '',
            '__EVENTARGUMENT': '',
            '__VIEWSTATE': state,
            '__EVENTVALIDATION': valid,
            'ctl00$ContentPlaceHolder1$Hidden1': '',
            'RadioButtonUnpaid': '0',
            'ctl00$ContentPlaceHolder1$payButtonWaitConfirm': u'网银付款',
        }
        r = rebot.http_post(url, headers=headers,cookies=cookies, data=data, timeout=128)
        soup = bs(r.content, 'lxml')
        #errmsg = soup.find_all('script')[-1].get_text()
        try:
            info = soup.find('table', attrs={'id': 'ContentPlaceHolder1_GridView3'}).find_all('tr')[1].find_all('td')
            sn = info[1].get_text()
            pay_money = float(info[7].get_text())
        except:
            sn = ''
            pay_money = ''
        url = 'http://ticket.qdjyjt.com/FrontPay.aspx'
        r = rebot.http_get(url, headers=headers, cookies=cookies)
        soup = bs(r.content, 'lxml')
        state = soup.find('input', attrs={'id': '__VIEWSTATE'}).get('value', '')
        valid = soup.find('input', attrs={'id': '__EVENTVALIDATION'}).get('value', '')
        # pay_money = float(soup.find('span', attrs={'id': 'ContentPlaceHolder1_Label2'}).get_text())
        # rebot_log.info(soup)
        if sn and r.ok and pay_money:
            cks = json.dumps(dict(cookies))
            order.modify(extra_info={'pcode': tpass, 'cookies': cks, 'state': state, 'valid': valid, 'pay_money': pay_money, 'sn': sn})
            expire_time = dte.now() + datetime.timedelta(seconds=15 * 60)
            lock_result.update({
                'result_code': 1,
                'raw_order_no': sn,
                "expire_datetime": expire_time,
                "source_account": rebot.telephone,
                'pay_money': 0,
            })
            return lock_result

        return
        if '车次错误,请您重新选择其他车次' in errmsg:
            errmsg = re.findall(r'\'\S+\'', errmsg)[0].split("'")[1]
            lock_result.update({
                'result_code': 0,
                "result_reason": errmsg,
            })
            return lock_result

    def send_order_request(self, order):
        rebot = order.get_lock_rebot()
        v = rebot.check_login()
        if not v:
            return
        sn = order.pay_order_no
        url = 'http://ticket.qdjyjt.com/'
        cookies = json.loads(rebot.cookies)
        headers = {
            'User-Agent': rebot.user_agent,
            'Content-Type': 'application/x-www-form-urlencoded',
        }
        data = {
            '__EVENTTARGET': 'ctl00$ContentPlaceHolder1$LinkButton10',
            '__EVENTARGUMENT': '',
            '__VIEWSTATE': v[1],
            '__EVENTVALIDATION': v[2],
            'ctl00$ContentPlaceHolder1$DropDownList3': '-1',
            'ctl00$ContentPlaceHolder1$chengchezhan_id': '',
            'destination-id': '',
            'ctl00$ContentPlaceHolder1$mudizhan_id': '',
            'tripDate': '请选择',
            'ctl00$ContentPlaceHolder1$chengcheriqi_id': '',
            'ctl00$ContentPlaceHolder1$chengcheriqi_id0': '',
        }
        r = rebot.http_post(url, headers=headers, cookies=cookies, data=data)
        soup = bs(r.content, 'lxml')
        state = soup.find('input', attrs={'id': '__VIEWSTATE'}).get('value', '')
        valid = soup.find('input', attrs={'id': '__EVENTVALIDATION'}).get('value', '')
        data = {}
        data = {
            '__EVENTTARGET': '',
            '__EVENTARGUMENT': '',
            '__VIEWSTATE': state,
            '__EVENTVALIDATION': valid,
            'ctl00$ContentPlaceHolder1$ButtonUnpaidOrderSearch': '订单明细查询',
        }
        r = rebot.http_post(url, headers=headers, cookies=cookies, data=data)
        soup = bs(r.content, 'lxml')
        state = soup.find('input', attrs={'id': '__VIEWSTATE'}).get('value', '')
        valid = soup.find('input', attrs={'id': '__EVENTVALIDATION'}).get('value', '')
        data = {}
        data = {
            '__EVENTTARGET': '',
            '__EVENTARGUMENT': '',
            '__VIEWSTATE': state,
            '__EVENTVALIDATION': valid,
            'ctl00$ContentPlaceHolder1$TextBox17': dte.now().strftime('%Y%m%d'),
            'ctl00$ContentPlaceHolder1$ButtonSearchPaidOrder': '按订单日期查询',
        }
        # rebot_log.info(data)
        r = rebot.http_post(url, headers=headers, cookies=cookies, data=data)
        #rebot_log.info(r.content)
        soup = bs(r.content, 'lxml')
        info = soup.find('table', attrs={'id': 'ContentPlaceHolder1_GridViewpaid'}).find_all('tr')
        # rebot_log.info(info)
        for x in info[1:]:
            y = x.find_all('td')
            sn1 = y[0].get_text().strip()
            # rebot_log.info(sn1)
            if sn == sn1:
                state = y[-2].get_text().strip()
                # rebot_log.info(state)
                return {
                    "state": state,
                    "pick_site": '',
                    'raw_order': sn,
                    "pay_money": 0.0,
                }
        return {
            "state": '未付款',
            "pick_site": '',
            'raw_order': sn,
            "pay_money": 0.0,
        }


    # 刷新出票
    def do_refresh_issue(self, order):
        result_info = {
            "result_code": 0,
            "result_msg": "",
            "pick_code_list": [],
            "pick_msg_list": [],
        }
        # if not self.need_refresh_issue(order):
        #     result_info.update(result_msg="状态未变化")
        #     return result_info
        ret = self.send_order_request(order)
        state = ret['state']
        raw_order = ret['raw_order']
        if '已取消' in state:
            result_info.update({
                "result_code": 5,
                "result_msg": state,
            })
        elif '已付款订单' == state:
            dx_info = {
                "time": order.drv_datetime.strftime("%Y-%m-%d %H:%M"),
                "start": order.line.s_sta_name,
                "end": order.line.d_sta_name,
                'raw_order': raw_order,
            }
            dx_tmpl = DUAN_XIN_TEMPL[SOURCE_QDKY]
            code_list = ["%s" % (raw_order)]
            msg_list = [dx_tmpl % dx_info]
            result_info.update({
                "result_code": 1,
                "result_msg": state,
                "pick_code_list": code_list,
                "pick_msg_list": msg_list,
            })
        return result_info

    # 线路刷新, java接口调用
    def do_refresh_line(self, line):
        now = dte.now()
        state, valid, cookies = self.update_state()
        data = {
            '__EVENTTARGET': '',
            '__EVENTARGUMENT': '',
            '__VIEWSTATE': state,
            '__EVENTVALIDATION': valid,
            'DropDownList2': line.drv_date,
            'city2': line.d_city_name,
            'ImageButton1.x': '24',
            'ImageButton1.y': '16',
        }
        url = 'http://www.qdjyjt.com/infor/select1.aspx'
        ua = random.choice(BROWSER_USER_AGENT)
        headers = {"User-Agent": ua,
                   "Content-Type": "application/x-www-form-urlencoded"}
        r = requests.post(url, headers=headers, data=data)
        soup = bs(r.content, 'lxml')
        try:
            info = soup.find('table', attrs={'id': 'GridView2'}).find_all('tr', attrs={'style': True})
        except:
            result_info = {}
            result_info.update(result_msg="exception_ok", update_attrs={"left_tickets": 5, "refresh_datetime": now})
            return result_info
        crawl_source = "qdky"
        update_attrs = {}
        ft = Line.objects.filter(s_city_name=line.s_city_name,
                                 d_city_name=line.d_city_name, drv_date=line.drv_date)
        t = {x.line_id: x for x in ft}
        update_attrs = {}
        for x in info:
            try:
                y = x.find_all('td')
                bus_num = y[1].get_text().strip()
                drv_date = line.drv_date
                drv_time = y[2].get_text().strip()
                left_tickets = y[4].get_text().strip()
                full_price = y[6].get_text().strip()
                drv_datetime = dte.strptime("%s %s" % (drv_date, drv_time), "%Y-%m-%d %H:%M")
                line_id_args = {
                    's_city_name': line.s_city_name,
                    'd_city_name': line.d_city_name,
                    'bus_num': bus_num,
                    'crawl_source': crawl_source,
                    'drv_datetime': drv_datetime,
                }
                line_id = md5( "%(s_city_name)s-%(d_city_name)s-%(drv_datetime)s-%(bus_num)s-%(crawl_source)s" % line_id_args)
                if line_id in t:
                    t[line_id].update(**{"left_tickets": left_tickets, 'full_price': full_price, "refresh_datetime": now})
                if line_id == line.line_id and int(left_tickets):
                    update_attrs = {"left_tickets": left_tickets, 'full_price': full_price, "refresh_datetime": now}
            except:
                pass

        result_info = {}
        if not update_attrs:
            result_info.update(result_msg="no line info", update_attrs={"left_tickets": 0, "refresh_datetime": now})
        else:
            result_info.update(result_msg="ok", update_attrs=update_attrs)
        return result_info

    def get_pay_page(self, order, valid_code="", session=None, pay_channel="alipay", **kwargs):
        rebot = order.get_lock_rebot()
        is_login = rebot.test_login_status()
        if not rebot.ip:
            try:
                rebot.proxy_ip()
            except:
                pass
        rebot_log.info(rebot.ip)

        # 登录验证码
        if valid_code and not is_login:
            key = "pay_login_info_%s_%s" % (
                order.order_no, order.source_account)
            info = json.loads(session[key])
            headers = info["headers"]
            cookies = info["cookies"]
            params = {
                "ctl00$ContentPlaceHolder1$txtyhm": rebot.telephone,
                "ctl00$ContentPlaceHolder1$txtmm": rebot.password,
                "ctl00$ContentPlaceHolder1$checktxt1": valid_code,
                '__EVENTVALIDATION': info['valid'],
                '__VIEWSTATE': info['state'],
                '__EVENTTARGET': '',
                '__EVENTARGUMENT': '',
                'ctl00$ContentPlaceHolder1$Button_4_dl': '登 录',
            }
            custom_headers = {}
            custom_headers.update(headers)
            custom_headers.update({
                'Content-Type': 'application/x-www-form-urlencoded',
                'Referer': 'http://ticket.qdjyjt.com/',
                'Host': 'ticket.qdjyjt.com',
            })
            r = rebot.http_post('http://ticket.qdjyjt.com/',
                                data=urllib.urlencode(params),
                                headers=custom_headers,
                                # allow_redirects=False,
                                cookies=cookies)
            soup = bs(r.content, 'lxml')
            tel = soup.find('a', attrs={'id': 'ContentPlaceHolder1_LinkButtonLoginMemu'}).get_text().strip()
            rebot_log.info(tel)
            if tel != '登录':
                cookies.update(dict(r.cookies))
                rebot.modify(cookies=json.dumps(cookies))

        is_login = is_login or rebot.test_login_status()
        if is_login:
            if order.status in [STATUS_LOCK_RETRY, STATUS_WAITING_LOCK]:
                self.lock_ticket(order, valid_code=valid_code)
                order.reload()
                fail_msg = order.lock_info.get("fail_reason", "")
                if fail_msg == "input_code":
                    valid_url = 'http://ticket.qdjyjt.com/yzm.aspx'
                    data = {
                        "cookies": json.loads(rebot.cookies),
                        "headers": {"User-Agent": rebot.user_agent},
                        "valid_url": valid_url,
                    }
                    key = "pay_login_info_%s_%s" % (
                        order.order_no, order.source_account)
                    session[key] = json.dumps(data)
                    return {"flag": "input_code", "content": ""}

            if order.status == STATUS_WAITING_ISSUE:
                pay_url = 'http://ticket.qdjyjt.com/FrontPay.aspx'
                headers = {
                    "User-Agent": rebot.user_agent,
                    "Content-Type": "application/x-www-form-urlencoded",
                }
                cookies = json.loads(order.extra_info.get('cookies'))
                data = {
                    '__VIEWSTATE': order.extra_info.get('state'),
                    '__EVENTVALIDATION': order.extra_info.get('valid'),
                    'ctl00$ContentPlaceHolder1$ImageButton3.x': '65',
                    'ctl00$ContentPlaceHolder1$ImageButton3.y': '30',
                }
                r = rebot.http_post(pay_url, headers=headers, data=data, cookies=cookies)
                pay_money = order.extra_info.get('pay_money')
                trade_no = order.extra_info.get('sn')
                # rebot_log.info(r.content)
                if order.pay_money != pay_money or order.pay_order_no != trade_no:
                    order.modify(pay_money=pay_money, pay_order_no=trade_no, pay_channel='alipay')
                return {"flag": "html", "content": r.content}

        # 未登录
        if not is_login:
            ua = random.choice(BROWSER_USER_AGENT)
            headers = {"User-Agent": ua}
            url = 'http://ticket.qdjyjt.com/'
            r = rebot.http_get(url, headers=headers)
            soup = bs(r.content, 'lxml')
            state = soup.find('input', attrs={'id': '__VIEWSTATE'}).get('value', '')
            valid = soup.find('input', attrs={'id': '__EVENTVALIDATION'}).get('value', '')
            data = {
                '__EVENTTARGET': 'ctl00$ContentPlaceHolder1$LinkButtonLoginMemu',
                '__EVENTARGUMENT': '',
                '__VIEWSTATE': state,
                '__EVENTVALIDATION': valid,
                'ctl00$ContentPlaceHolder1$DropDownList3': '-1',
                'ctl00$ContentPlaceHolder1$chengchezhan_id': '',
                'destination-id': '',
                'ctl00$ContentPlaceHolder1$mudizhan_id': '',
                'tripDate': '请选择',
                'ctl00$ContentPlaceHolder1$chengcheriqi_id': '',
                'ctl00$ContentPlaceHolder1$chengcheriqi_id0': '',
            }
            r = rebot.http_post(url, headers=headers, data=data, cookies=r.cookies)
            soup = bs(r.content, 'lxml')
            state = soup.find('input', attrs={'id': '__VIEWSTATE'}).get('value', '')
            valid = soup.find('input', attrs={'id': '__EVENTVALIDATION'}).get('value', '')

            valid_url = 'http://ticket.qdjyjt.com/yzm.aspx'
            data = {
                "cookies": {},
                "headers": headers,
                "valid_url": valid_url,
                'state': state,
                'valid': valid,
            }
            key = "pay_login_info_%s_%s" % (
                order.order_no, order.source_account)
            session[key] = json.dumps(data)
            return {"flag": "input_code", "content": ""}
