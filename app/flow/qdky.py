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

    def do_lock_ticket(self, order, valid_code="", state='', valid=''):
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
        if len(order.riders) > 3:
            lock_result.update({
                'result_code': 0,
                'result_reason': '超过3位乘客，不允许下单',
            })
            return lock_result
        add_info = self.request_add_riders(order, rebot, state, valid)
        if add_info.get('error_code', ''):
            lock_result.update({
                'result_code': 2,
                'result_reason': add_info.get('errmsg', ''),
            })
            return lock_result
        res = self.send_lock_requests(order, rebot, add_info, valid_code)
        lock_result.update({"lock_info": res})
        if res.get('order_no', ''):
            expire_time = dte.now() + datetime.timedelta(seconds=15 * 60)
            lock_result.update({
                'result_code': 1,
                'raw_order_no': res['order_no'],
                "expire_datetime": expire_time,
                "source_account": rebot.telephone,
                'pay_money': res['pay_money'],
            })
            return lock_result
        else:
            print res
            if '已经使用此身份证预订过' in res.get('result_reason', ''):
                lock_result.update({
                        "result_code": 0,
                        "source_account": rebot.telephone,
                        "result_reason": res.get('result_reason', ''),
                    })
                return lock_result
            lock_result.update({
                'result_code': 2,
                "result_reason": res.get('result_reason', ''),
            })
            return lock_result

    def send_lock_requests(self, order, rebot, add_info, valid_code):
        pk = len(order.riders)
        url = 'http://ticket.qdjyjt.com/'
        res = {}
        errmsg = ''
        cookies = json.loads(rebot.cookies)
        headers = {
            'User-Agent': rebot.user_agent,
            'Content-Type': 'application/x-www-form-urlencoded',
            "Upgrade-Insecure-Requests":"1"
        }
        headers['Referer'] = 'http://ticket.qdjyjt.com/'
        headers['Host'] = 'ticket.qdjyjt.com'
        tpass = random.randint(111111, 999999)
        data = {
            '__EVENTTARGET': '',
            '__EVENTARGUMENT': '',
            '__VIEWSTATE': add_info['state'],
            '__EVENTVALIDATION': add_info['valid'],
            'ctl00$ContentPlaceHolder1$DropDownList1': pk,
            'MyRadioButton': add_info['btn'],
            'ctl00$ContentPlaceHolder1$GridView1$ctl%s$txtpwd' % (str(int(add_info['btn'])+2).zfill(2)): str(tpass),
            'ctl00$ContentPlaceHolder1$checktxt2': valid_code,
            'ctl00$ContentPlaceHolder1$show': u'提交订单',
        }
        time.sleep(1)
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
        try:
            time.sleep(3)
            r = rebot.http_post(url, headers=headers, cookies=cookies, data=data, timeout=30)
            soup = bs(r.content, 'lxml')
            state = soup.find('input', attrs={'id': '__VIEWSTATE'}).get('value', '')
            valid = soup.find('input', attrs={'id': '__EVENTVALIDATION'}).get('value', '')
            cookies.update(dict(r.cookies))
            try:
                errmsg = soup.find_all('script')[-1].get_text()
            except:
                rebot.modify(ip='')
                errmsg = '锁票 网络异常'
        except:
            res.update({
                "result_reason": errmsg or '验证码错误',
                "fail_type": errmsg or 'input_code',
            })
            return res
        if u'验证码错误' in r.content.decode('utf-8'):
            res.update({
                "result_reason": '验证码错误',
                "fail_type": 'input_code',
            })
            return res
        data = {
            '__EVENTTARGET': '',
            '__EVENTARGUMENT': '',
            '__VIEWSTATE': state,
            '__EVENTVALIDATION': valid,
            'ctl00$ContentPlaceHolder1$Hidden1': '',
            'RadioButtonUnpaid': '0',
            'ctl00$ContentPlaceHolder1$payButtonWaitConfirm': u'网银付款',
        }
        order_no = ''
        pay_money = 0
        try:
            time.sleep(1)
            r = rebot.http_post(url, headers=headers, cookies=cookies, data=data,timeout=30)
            soup = bs(r.content, 'lxml')
            info = soup.find('table', attrs={'id': 'ContentPlaceHolder1_GridView3'}).find_all('tr')[1].find_all('td')
            order_no = info[1].get_text()
            pay_money = float(info[7].get_text())
            cookies.update(dict(r.cookies))
            try:
                errmsg = soup.find_all('script')[-1].get_text()
                errmsg = re.findall(r'\'\S+\'', errmsg)[0].split("'")[1]
            except:
                rebot.modify(ip='')
                errmsg = '网银付款'
        except:
            res.update({
                'result_reason': errmsg,
                "fail_type": '网银付款',
            })
            return res

        url = 'http://ticket.qdjyjt.com/FrontPay.aspx'
        r = rebot.http_get(url, headers=headers, cookies=cookies)
        cookies.update(dict(r.cookies))
        soup = bs(r.content, 'lxml')
        state = soup.find('input', attrs={'id': '__VIEWSTATE'}).get('value', '')
        valid = soup.find('input', attrs={'id': '__EVENTVALIDATION'}).get('value', '')
        extra_info = {'pcode': tpass,
                      'cookies': json.dumps(dict(cookies)),
                      'state': state,
                      'valid': valid
                      }
        if order_no and r.ok and pay_money:
            res.update({'order_no': order_no, "pay_money": pay_money})
            order.modify(extra_info=extra_info)
            return res
        else:
            try:
                errmsg = soup.find_all('script')[-1].get_text()
                errmsg = re.findall(r'\'\S+\'', errmsg)[0].split("'")[1]
            except:
                errmsg = '网络异常2'
            res.update({
                'result_reason': errmsg,
                "fail_type": '最后付款',
            })
            return res

    def request_add_riders(self, order, rebot, state, valid):
        contact_info = order.contact_info
        cookies = json.loads(rebot.cookies)
        url = 'http://ticket.qdjyjt.com/'
        headers = {
            'User-Agent': rebot.user_agent,
            'Content-Type': 'application/x-www-form-urlencoded',
        }
        line = order.line
        sch_data = {
            '__EVENTTARGET': '',
            '__EVENTARGUMENT': '',
            '__VIEWSTATE': state,
            '__EVENTVALIDATION': valid,
            'ctl00$ContentPlaceHolder1$DropDownList3': unicode(line.extra_info['s_station_name']),
            'ctl00$ContentPlaceHolder1$chengchezhan_id': line.extra_info['s_station_name'][0],
            'destination-id': line.d_city_id,
            'ctl00$ContentPlaceHolder1$mudizhan_id': '',
            'tripDate': line.drv_date.replace('-', '/'),
            'ctl00$ContentPlaceHolder1$chengcheriqi_id': '',
            'ctl00$ContentPlaceHolder1$chengcheriqi_id0': '',
            'ctl00$ContentPlaceHolder1$Button_1_cx': '车次查询',
        }
        try:
            r = rebot.http_post(url, headers=headers, cookies=cookies, data=sch_data)
            soup = bs(r.content, "lxml")
            info = soup.find('table', attrs={'id': 'ContentPlaceHolder1_GridViewbc'}).find_all('tr')
            state = soup.find('input', attrs={'id': '__VIEWSTATE'}).get('value', '')
            valid = soup.find('input', attrs={'id': '__EVENTVALIDATION'}).get('value', '')
            cookies.update(dict(r.cookies))
        except:
            rebot.modify(ip='')
            try:
                errmsg = soup.find_all('script')[-1].get_text()
                errmsg = re.findall(r'\'\S+\'', errmsg)[0].split("'")[1]
            except:
                errmsg = ''
            return {'error_code': '1', "errmsg": "车次查询异常"+errmsg}
        tbc = ''
        for y in info[1:]:
            z = y.find_all('td')
            bus_num = z[1].get_text().strip()
            drv_time = z[2].get_text().strip()
            if bus_num == line.bus_num and drv_time == line.drv_time:
                tbc = y.find('input', attrs={'id': True, 'value': '预订'}).get('name', '')
        if not tbc:
            return {'error_code': '2', "errmsg": "找不到此班次"}
        time.sleep(0.5)
        cli_data = {
            '__EVENTTARGET': '',
            '__EVENTARGUMENT': '',
            '__EVENTVALIDATION': valid,
            '__VIEWSTATE': state,
            tbc: '预订',
            'ctl00$ContentPlaceHolder1$DropDownList3': '-1',
            'ctl00$ContentPlaceHolder1$chengchezhan_id': line.extra_info['s_station_name'][0],
            'destination-id': '',
            'ctl00$ContentPlaceHolder1$mudizhan_id': line.d_city_id,
            'tripDate': '请选择',
            'ctl00$ContentPlaceHolder1$chengcheriqi_id': line.drv_date.replace('-', ''),
            'ctl00$ContentPlaceHolder1$chengcheriqi_id0': line.drv_date.replace('-', '/'),
        }
        try:
            r = rebot.http_post(url, headers=headers, cookies=cookies, data=urllib.urlencode(cli_data))
            cookies.update(dict(r.cookies))
            soup = bs(r.content, "lxml")
            state = soup.find('input', attrs={'id': '__VIEWSTATE'}).get('value', '')
            valid = soup.find('input', attrs={'id': '__EVENTVALIDATION'}).get('value', '')
            info = soup.find('table', attrs={'id': 'ContentPlaceHolder1_GridView1'}).find_all('tr')
            for y in info[1:]:
                uid = y.find_all('span', attrs={'id': re.compile(r'ContentPlaceHolder1_GridView1_Label\S+')})[2].get_text().strip()
                if uid == contact_info['id_number']:
                    btn = y.find('input', attrs={'name': 'MyRadioButton', 'onclick': 'getRadio()'}).get('value', '')
                    rebot.modify(cookies=json.dumps(cookies))
                    return {"btn": btn, 'state': state, "valid": valid}
        except:
            rebot.modify(ip='')
            try:
                errmsg = soup.find_all('script')[-1].get_text()
                errmsg = re.findall(r'\'\S+\'', errmsg)[0].split("'")[1]
            except:
                errmsg = ''
            return {'error_code': '3', "errmsg": "预订"+errmsg}
        data = {
            '__EVENTTARGET': 'ctl00$ContentPlaceHolder1$LinkButtonXiugai',
            '__EVENTARGUMENT': '',
            '__VIEWSTATE': state,
            '__EVENTVALIDATION': valid,
            'ctl00$ContentPlaceHolder1$DropDownList1': '1',
            'ctl00$ContentPlaceHolder1$checktxt2': '',
        }
        time.sleep(0.5)
        r = rebot.http_post(url, headers=headers, cookies=cookies, data=data)
        cookies.update(dict(r.cookies))
        soup = bs(r.content, "lxml")
        state = soup.find('input', attrs={'id': '__VIEWSTATE'}).get('value', '')
        valid = soup.find('input', attrs={'id': '__EVENTVALIDATION'}).get('value', '')
        btn = soup.find('input', attrs={'id': 'ContentPlaceHolder1_GridView1_btnInsert'}).get('name', '')
        btn = '$'.join(btn.split('$')[:-1])
        sex = u'男'
        if int(contact_info['id_number'][-2]) % 2 == 0:
            sex = u'女'
        con_data = {
            '__EVENTTARGET': '',
            '__EVENTARGUMENT': '',
            '__VIEWSTATE': state,
            '__EVENTVALIDATION': valid,
            'ctl00$ContentPlaceHolder1$DropDownList1': '1',
            '%s$txtname' % btn: contact_info['name'],
            '%s$drpsex' % btn: sex,
            '%s$txtsfz' % btn: contact_info['id_number'],
            '%s$txttel' % btn: contact_info['telephone'],
            '%s$btnInsert' % btn: u'添加',
            'ctl00$ContentPlaceHolder1$checktxt2': '',
        }
        time.sleep(0.5)
        r = rebot.http_post(url, headers=headers, cookies=cookies, data=urllib.urlencode(con_data))
        cookies.update(dict(r.cookies))
        soup = bs(r.content, 'lxml')
        state = soup.find('input', attrs={'id': '__VIEWSTATE'}).get('value', '')
        valid = soup.find('input', attrs={'id': '__EVENTVALIDATION'}).get('value', '')
        x = order.contact_info
        info = soup.find('table', attrs={'id': 'ContentPlaceHolder1_GridView1'}).find_all('tr')
#         info1 = soup.find_all('script')[-1]
        for y in info[1:]:
            uid = y.find_all('span', attrs={'id': re.compile(r'ContentPlaceHolder1_GridView1_Label\S+')})[2].get_text().strip()
            if uid == x['id_number']:
                btn = y.find('input', attrs={'name': 'MyRadioButton', 'onclick': 'getRadio()'}).get('value', '')
                rebot.modify(cookies=json.dumps(cookies))
                return {"btn": btn, 'state': state, "valid": valid}

    def send_order_request(self, order):
        rebot = order.get_lock_rebot()
        res = rebot.check_login()
        if not res or not res.get('is_login', 0):
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
            '__VIEWSTATE': res['state'],
            '__EVENTVALIDATION': res['valid'],
            'ctl00$ContentPlaceHolder1$DropDownList3': '-1',
            'ctl00$ContentPlaceHolder1$chengchezhan_id': '',
            'destination-id': '',
            'ctl00$ContentPlaceHolder1$mudizhan_id': '',
            'tripDate': '请选择',
            'ctl00$ContentPlaceHolder1$chengcheriqi_id': '',
            'ctl00$ContentPlaceHolder1$chengcheriqi_id0': '',
        }
        time.sleep(2)
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
        time.sleep(2)
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
        time.sleep(2)
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
        time.sleep(random.choice([3, 5, 10, 15, 20]))
        ret = self.send_order_request(order)
        #ret = {'state': '已付款订单', 'raw_order':order.raw_order_no}
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
                code_list.append(str(pcode))
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
            r = rebot.http_get(url, headers=headers, timeout=5)
            soup = bs(r.content, 'lxml')
            params = {
                "__EVENTARGUMENT": soup.select("#__EVENTARGUMENT")[0].get("value"),
                "__EVENTTARGET": soup.select("#__EVENTTARGET")[0].get("value"),
                "__EVENTVALIDATION": soup.select("#__EVENTVALIDATION")[0].get("value"),
                "__VIEWSTATE": soup.select("#__VIEWSTATE")[0].get("value"),
            }
        except:
            now = dte.now()
            result_info.update(result_msg="except_ok", update_attrs={"left_tickets": 5,"refresh_datetime": now})
            return result_info
        data = {}
        data.update(params)
        data.update({
            'ctl00$ContentPlaceHolder1$DropDownList3': unicode(line.extra_info['s_station_name']),
            'ctl00$ContentPlaceHolder1$chengchezhan_id': line.extra_info['s_station_name'][0],
            'destination-id': unicode(line.d_city_id),
            'ctl00$ContentPlaceHolder1$mudizhan_id': line.d_city_id,
            'tripDate': unicode(line.drv_date.replace('-', '/')),
            'ctl00$ContentPlaceHolder1$chengcheriqi_id': line.drv_date.replace('-', ''),
            'ctl00$ContentPlaceHolder1$chengcheriqi_id0': line.drv_date.replace('-', '/'),
            'ctl00$ContentPlaceHolder1$Button_1_cx': u'车次查询',
        })
        try:
            r = rebot.http_post(url, data=data, headers=headers, timeout=8)
        except:
            now = dte.now()
            result_info.update(result_msg="except_ok2", update_attrs={"left_tickets": 5, "refresh_datetime": now})
            return result_info
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
        is_login = False
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
            url = 'http://ticket.qdjyjt.com/'
            try:
                r = rebot.http_post(url, data=urllib.urlencode(params),headers=custom_headers,cookies=cookies)
                soup = bs(r.content, 'lxml')
                tel = soup.find('a', attrs={'id': 'ContentPlaceHolder1_LinkButtonLoginMemu'}).get_text().strip()
                if rebot.telephone == tel:
                    cookies.update(dict(r.cookies))
                    rebot.modify(cookies=json.dumps(cookies))
                    is_login = True
                else:
                    rebot.modify(cookies='{}', ip='')
            except:
                rebot.modify(ip='')
        res = rebot.check_login()
        if res and res.get('is_login', 0):
            is_login = True
        if is_login:
            if order.status in [STATUS_LOCK_RETRY, STATUS_WAITING_LOCK]:
                fail_type = ''
                state = res.get("state", '')
                valid = res.get('valid', '')
                if valid_code:
                    self.lock_ticket(order, valid_code=valid_code, state=state,valid=valid)
                    order.reload()
                    fail_type = order.lock_info.get("fail_type", "")
                if not valid_code or not valid or fail_type == "input_code":
                    valid_url = 'http://ticket.qdjyjt.com/yzm.aspx'
                    data = {
                        "cookies": json.loads(rebot.cookies),
                        "headers": {"User-Agent": rebot.user_agent},
                        "valid_url": valid_url,
                        'state': state,
                        'valid': state,
                    }
                    key = "pay_login_info_%s_%s" % (order.order_no, order.source_account)
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
            state = res.get("state", '')
            valid = res.get('valid', '')
            headers = {
                    'User-Agent': rebot.user_agent,
                    "Upgrade-Insecure-Requests": 1,
                    }
            cookies = json.loads(rebot.cookies) or {}
            url = 'http://ticket.qdjyjt.com/'
            if not state or not valid:
                r = rebot.http_get(url, headers=headers)
                cookies.update(dict(r.cookies))
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
            r = rebot.http_post(url, headers=headers, data=data, cookies=cookies)
            cookies.update(dict(r.cookies))
            soup = bs(r.content, 'lxml')
            state = soup.find('input', attrs={'id': '__VIEWSTATE'}).get('value', '')
            valid = soup.find('input', attrs={'id': '__EVENTVALIDATION'}).get('value', '')
            valid_url = 'http://ticket.qdjyjt.com/yzm.aspx'
            data = {
                "cookies": cookies,
                "headers": headers,
                "valid_url": valid_url,
                'state': state,
                'valid': valid,
            }
            key = "pay_login_info_%s_%s" % (order.order_no, order.source_account)
            session[key] = json.dumps(data)
            return {"flag": "input_code", "content": ""}
