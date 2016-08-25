# coding=utf-8

import requests
import re
import time
import json
import urllib

import datetime
import random
from bs4 import BeautifulSoup as bs

from app.constants import *
from datetime import datetime as dte
from app.flow.base import Flow as BaseFlow
from app.models import Line
from app.utils import md5
from app import rebot_log
# import cStringIO
from time import sleep
from app.models import QdkyWebRebot


class Flow(BaseFlow):
    name = 'qdky'

    def do_lock_ticket(self, order, valid_code=""):
        lock_result = {
            "lock_info": {},
            "source_account": order.source_account,
            "result_code": -1,
            "result_reason": "",
            "pay_url": "",
            "raw_order_no": "",
            "expire_datetime": "",
            "pay_money": 0,
        }
        rebot = order.get_lock_rebot()
        res = rebot.add_riders(order)
        if res[0] == '-1':
            lock_result.update({
                'result_code': 2,
                'result_reason': res[1],
            })
            return lock_result
        pk = len(order.riders)
        tpass = random.randint(111111, 999999)
        data = {
            '__EVENTTARGET': '',
            '__EVENTARGUMENT': '',
            '__VIEWSTATE': res[1],
            '__EVENTVALIDATION': res[2],
            'ctl00$ContentPlaceHolder1$DropDownList1': pk,
            'MyRadioButton': res[0],
            'ctl00$ContentPlaceHolder1$GridView1$ctl%s$txtpwd' %(str(int(res[0])+2).zfill(2)): str(tpass),
            'ctl00$ContentPlaceHolder1$checktxt2': valid_code,
            'ctl00$ContentPlaceHolder1$show': u'提交订单',
        }
        url = 'http://ticket.qdjyjt.com/'
        cookies = json.loads(rebot.cookies)
        headers = {
            'User-Agent': rebot.user_agent,
            'Content-Type': 'application/x-www-form-urlencoded',
        }
        r = rebot.http_post(url, headers=headers, cookies=cookies, data=data, timeout=30)
        soup = bs(r.content, 'lxml')
        state = soup.find('input', attrs={'id': '__VIEWSTATE'}).get('value', '')
        valid = soup.find('input', attrs={'id': '__EVENTVALIDATION'}).get('value', '')
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
        r = rebot.http_post(url, headers=headers, cookies=cookies, data=urllib.urlencode(data), timeout=30)
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
        if u'验证码错误' in r.content.decode('utf-8'):
            lock_result.update({
                'result_code': 2,
                "result_reason": '验证码错误',
            })
            return lock_result
        data = {
            '__EVENTTARGET': '',
            '__EVENTARGUMENT': '',
            '__VIEWSTATE': state,
            '__EVENTVALIDATION': valid,
            'ctl00$ContentPlaceHolder1$Hidden1': '',
            'RadioButtonUnpaid': '0',
            'ctl00$ContentPlaceHolder1$payButtonWaitConfirm': u'网银付款',
        }
        r = rebot.http_post(url, headers=headers,
                            cookies=cookies, data=data, timeout=30)
        soup = bs(r.content, 'lxml')
        
        try:
            info = soup.find('table', attrs={'id': 'ContentPlaceHolder1_GridView3'}).find_all('tr')[1].find_all('td')
            order_no = info[1].get_text()
            pay_money = float(info[7].get_text())
        except:
            order_no = ''
            pay_money = 0
        url = 'http://ticket.qdjyjt.com/FrontPay.aspx'
        r = rebot.http_get(url, headers=headers, cookies=cookies)
        soup = bs(r.content, 'lxml')
        state = soup.find('input', attrs={'id': '__VIEWSTATE'}).get('value', '')
        valid = soup.find('input', attrs={'id': '__EVENTVALIDATION'}).get('value', '')

        if order_no and r.ok and pay_money:
            order.modify(extra_info={'pcode': tpass,
                                     'cookies': json.dumps(dict(cookies)),
                                     'state': state,
                                     'valid': valid
                                     }
                         )
            expire_time = dte.now() + datetime.timedelta(seconds=15 * 60)
            lock_result.update({
                'result_code': 1,
                'raw_order_no': order_no,
                "expire_datetime": expire_time,
                "source_account": rebot.telephone,
                'pay_money': pay_money,
            })
            return lock_result
        else:
            try:
                errmsg = soup.find_all('script')[-1].get_text()
            except:
                errmsg = ''
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
        data = {
            '__EVENTTARGET': '',
            '__EVENTARGUMENT': '',
            '__VIEWSTATE': state,
            '__EVENTVALIDATION': valid,
            'ctl00$ContentPlaceHolder1$TextBox17': dte.now().strftime('%Y%m%d'),
            'ctl00$ContentPlaceHolder1$ButtonSearchPaidOrder': '按订单日期查询',
        }
        r = rebot.http_post(url, headers=headers, cookies=cookies, data=data)
        soup = bs(r.content, 'lxml')
        info = soup.find('table', attrs={'id': 'ContentPlaceHolder1_GridViewpaid'}).find_all('tr')
        for x in info[1:]:
            y = x.find_all('td')
            order_no = y[0].get_text().strip()
            if order.raw_order_no == order_no:
                state = y[-2].get_text().strip()
                return {
                    "state": state,
                    'raw_order': order_no,
                }

    # 刷新出票
    def do_refresh_issue(self, order):
        result_info = {
            "result_code": 0,
            "result_msg": "",
            "pick_code_list": [],
            "pick_msg_list": [],
        }
        ret = self.send_order_request(order)
        state = ret['state']
        raw_order = ret['raw_order']
        pcode = order.extra_info.get("pcode", '')
        if '已付款订单' == state:
            dx_info = {
                "time": order.drv_datetime.strftime("%Y-%m-%d %H:%M"),
                "start": "%s(%s)" % (order.line.s_city_name, order.line.s_sta_name),
                "end": order.line.d_sta_name,
                'raw_order': raw_order,
                "code": pcode
            }
            code_list = []
            if pcode:
                code_list.append(pcode)
            else:
                code_list.append('无需取票密码')
            dx_tmpl = DUAN_XIN_TEMPL[SOURCE_QDKY]
            msg_list = [dx_tmpl % dx_info]
            result_info.update({
                "result_code": 1,
                "result_msg": state,
                "pick_code_list": code_list,
                "pick_msg_list": msg_list,
            })
#         elif '已取消' in state:
#             result_info.update({
#                 "result_code": 5,
#                 "result_msg": state,
#             })
        return result_info

    def do_refresh_line(self, line):
        now = dte.now()
        update_attrs = {}
        result_info = {"result_msg": "",
                       "update_attrs": {}
                       }
        url = "http://ticket.qdjyjt.com/"
        rebot = QdkyWebRebot.get_one()
        headers = {"User-Agent": rebot.user_agent,
                   "Content-Type": "application/x-www-form-urlencoded"}
        try:
            r = rebot.http_get(url, headers=headers)
            soup = bs(r.content, 'lxml')
            params = {
                "__EVENTARGUMENT": soup.select("#__EVENTARGUMENT")[0].get("value"),
                "__EVENTTARGET": soup.select("#__EVENTTARGET")[0].get("value"),
                "__EVENTVALIDATION": soup.select("#__EVENTVALIDATION")[0].get("value"),
                "__VIEWSTATE": soup.select("#__VIEWSTATE")[0].get("value"),
            }
        except:
            now = dte.now()
            result_info.update(result_msg="except_ok", 
                               update_attrs={"left_tickets": 5,
                                             "refresh_datetime": now})
            return result_info
        data = {}
        data.update(params)
        data.update({
            'ctl00$ContentPlaceHolder1$DropDownList3': unicode(line.extra_info['s_station_name']),
            'ctl00$ContentPlaceHolder1$chengchezhan_id': '',
            'destination-id': unicode(line.d_city_id),
            'ctl00$ContentPlaceHolder1$mudizhan_id': '',
            'tripDate': unicode(line.drv_date.replace('-', '/')),
            'ctl00$ContentPlaceHolder1$chengcheriqi_id': '',
            'ctl00$ContentPlaceHolder1$chengcheriqi_id0': '',
            'ctl00$ContentPlaceHolder1$Button_1_cx': u'车次查询',
        })
        r = rebot.http_post(url, data=data, headers=headers)
        soup = bs(r.content, 'lxml')
        scl_list = soup.find('table', attrs={'id': 'ContentPlaceHolder1_GridViewbc'})
        if scl_list:
            scl_list = scl_list.find_all('tr', attrs={'style': True})
            for x in scl_list[1:]:
                y = x.find_all('td')
                ticket_status = y[3].get_text().strip()
                left_tickets = 0
                if ticket_status == u"有票":
                    left_tickets = 45
                bus_num = y[1].get_text().strip()
                drv_time = y[2].get_text().strip()
                full_price = y[6].get_text().strip()
                drv_datetime = dte.strptime("%s %s" % (line.drv_date, drv_time), "%Y-%m-%d %H:%M")

                line_id_args = {
                    's_city_name': line.s_city_name,
                    'd_city_name': line.d_city_name,
                    'bus_num': bus_num,
                    'crawl_source': line.crawl_source,
                    'drv_datetime': drv_datetime,
                }
                line_id = md5("%(s_city_name)s-%(d_city_name)s-%(drv_datetime)s-%(bus_num)s-%(crawl_source)s" % line_id_args)
                try:
                    obj = Line.objects.get(line_id=line_id)
                except Line.DoesNotExist:
                    continue
                info = {
                    "full_price": float(full_price),
                    "fee": 0,
                    "left_tickets": left_tickets,
                    "refresh_datetime": now,
                }
                if line_id == line.line_id:
                    update_attrs = info
                if line_id == line.line_id and int(left_tickets):
                    obj.update(**info)
        if not update_attrs:
            result_info.update(result_msg="no line info", update_attrs={"left_tickets": 0, "refresh_datetime": now})
        else:
            result_info.update(result_msg="ok", update_attrs=update_attrs)
        return result_info

    def get_pay_page(self, order, valid_code="", session=None, pay_channel="alipay", **kwargs):
        rebot = order.get_lock_rebot()
        is_login = rebot.test_login_status()
        if valid_code and not is_login: # 登录验证码
            key = "pay_login_info_%s_%s" % (order.order_no, order.source_account)
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
            if rebot.telephone == tel:
                cookies.update(dict(r.cookies))
                rebot.modify(cookies=json.dumps(cookies))
                is_login = True
            else:
                rebot.modify(cookies='{}', ip='')
        if is_login:
            if order.status in [STATUS_LOCK_RETRY, STATUS_WAITING_LOCK]:
                fail_msg = ''
                if valid_code:
                    self.lock_ticket(order, valid_code=valid_code)
                    order.reload()
                    fail_msg = order.lock_info.get("fail_reason", "")
                if not valid_code or fail_msg == "input_code":
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
                    'ctl00$ContentPlaceHolder1$ImageButton1.x': '65',
                    'ctl00$ContentPlaceHolder1$ImageButton1.y': '30',
                 }
                r = rebot.http_post(pay_url, headers=headers, data=data, cookies=cookies)
                order.modify(pay_channel='yh')
                return {"flag": "html", "content": r.content}
        # 未登录
        if not is_login:
            headers = {
                'User-Agent': rebot.user_agent,
                "Upgrade-Insecure-Requests": 1,
            }
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
            key = "pay_login_info_%s_%s" % (order.order_no, order.source_account)
            session[key] = json.dumps(data)
            return {"flag": "input_code", "content": ""}
