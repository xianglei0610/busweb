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
from app.utils import md5, vcode_glcx
from app import rebot_log
# import cStringIO
from time import sleep


class Flow(BaseFlow):
    name = 'glcx'

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
        rebot = order.get_lock_rebot()
        line = order.line
        cookies = json.loads(rebot.cookies)
        headers = {
            'User-Agent': rebot.user_agent,
            "Content-Type": "application/x-www-form-urlencoded",
        }
        uname = order.contact_info['name']
        tel = order.contact_info['telephone']
        uid = order.contact_info['id_number']
        # url = 'http://www.0000369.cn/buytks!tobuy.action'
        # pa = 'bliid=%s+&bliidSendDatetime=%s+%s&\
        # portName=%s&arrivalPortID=%s&stationId=%s&\
        # CanSellNum=%s&startNo=%s&portPrice=%s&\
        # ticketDate=%s&\
        # sendTime=++++++++++++++++++++++%s++++++++++++++++++++++' %(line.bus_num, \
        #     line.drv_date, line.drv_time, line.d_city_name, \
        #     line.d_sta_id, line.s_sta_id, line.left_tickets, \
        #     line.extra_info['startNo'], line.full_price, \
        #     line.drv_date, line.drv_time)
        # pa = ''.join(pa.split())
        # rebot_log.info(pa)
        # pa = urllib.quote(pa.encode('utf-8'), safe='=&+')
        # r = requests.post(url, headers=headers, cookies=cookies, data=pa)
        # soup = bs(r.content, 'lxml')
        # info = soup.find('div', attrs={'class': 'buy'})
        # rebot_log.info(info)
        v = vcode_glcx(cookies)
        url = 'http://www.0000369.cn/buytks!toAffirm.action'
        pre = 'insuranceValue=2&name=%s&idcard=%s&\
        tel=%s&tkstype=0&insurance=0&' %(uname, uid, tel)
        rider = list(order.riders)
        pk = len(rider)
        for x in rider:
            if uid == x['id_number']:
                rider.remove(x)
        tmp = ''
        if pk > 1:
            for i, x in enumerate(rider):
                i += 2
                tmp += 'name=%s&idcard=%s&tel=%s&tkstype=0&\
                insurance=0&' %(x['name'], x['id_number'], x['telephone'])

        suf = 'rand=%s&bliid=%s+&sendTime=&stationId=%s&\
        bliidSendDatetime=%s+%s&arrivalPortID=%s&\
        customName=%s&customTelephone=%s&customIDCardNo=%s\
        &customAddress=&ticketDate=%s&startNo=%s&CanSellNum=%s\
        &ticketPrice=%s' %(v[0], line.bus_num, line.s_sta_id, line.drv_date,
            line.drv_time, line.d_sta_id, rebot.telephone, rebot.telephone, rebot.userid, line.drv_date,
            line.extra_info['startNo'], line.left_tickets, line.full_price)

        pa = pre + tmp + suf
        pa = ''.join(pa.split())
        # rebot_log.info(pa)
        pa = urllib.quote(pa.encode('utf-8'), safe='=&+')
        r = requests.post(url, headers=headers, cookies=cookies, data=pa)
        soup = bs(r.content, 'lxml')
        # rebot_log.info(soup)
        try:
            sn = soup.find('input', attrs={'id': 'dealOrder'}).get('value', '')
        except:
            sn = ''
        # rebot_log.info(cookies)
        # rebot_log.info(soup.title)
        # rebot_log.info(sn)
        if '确认支付' in soup.title and sn:
            expire_time = dte.now() + datetime.timedelta(seconds=15 * 60)
            # cookies = {}
            # for x, y in cks.items():
            #     cookies[x] = y
            order.modify(extra_info={
                'orderId': sn,
                'ticketDate': line.drv_date,
                'totalPirce': line.full_price * pk,
                'stationId': line.s_sta_id,
                'ticketNum': pk,
                'telephone': rebot.telephone,
                'userId': rebot.telephone,
            })
            lock_result.update({
                'result_code': 1,
                'raw_order_no': sn,
                "expire_datetime": expire_time,
                "source_account": rebot.telephone,
                'pay_money': 0,
            })
            return lock_result
        # elif fail_reason:
        #     lock_result.update({
        #         'result_code': 0,
        #         "lock_info": {"fail_reason": fail_reason}
        #     })
        #     return lock_result

    def send_order_request(self, order):
        rebot = order.get_lock_rebot()
        cookies = json.loads(rebot.cookies)
        sn = order.extra_info['orderId']
        url = 'http://www.0000369.cn/order!order.action'
        headers = {
            "User-Agent": rebot.user_agent,
        }
        r = requests.get(url, headers=headers, cookies=cookies)
        soup = bs(r.content, 'lxml')
        info = soup.find()
        for x in info:
            ocode = x['OrderCode']
            if sn == ocode:
                pcode = x.get('Password', '')
                state = x['OrderStatus']

        return {
            "state": state,
            "pick_no": pcode,
            "pick_code": pcode,
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
        elif '失败' in state:
            result_info.update({
                "result_code": 2,
                "result_msg": state,
            })
        elif '已付款确认' in state and code:
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
            }
            dx_tmpl = DUAN_XIN_TEMPL[SOURCE_HN96520]
            code_list = ["%s" % (code)]
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
        data = {
            'stationId': line.s_sta_id,
            'portId': line.d_sta_id,
            'startTime': line.drv_date,
        }
        ua = random.choice(BROWSER_USER_AGENT)
        headers = {
            "User-Agent": ua,
            'Content-Type': 'application/x-www-form-urlencoded',
            'X-Requested-With': 'XMLHttpRequest',
        }
        url = 'http://www.0000369.cn/buytks!searchtks.action'
        r = requests.post(url, headers=headers, data=urllib.urlencode(data))
        now = dte.now()
        update_attrs = {}
        ft = Line.objects.filter(s_city_name=line.s_city_name,
                                 d_city_name=line.d_city_name, drv_date=line.drv_date)
        t = {x.line_id: x for x in ft}
        update_attrs = {}
        soup = bs(r.content, 'lxml')
        info = soup.find('table', attrs={'id': 'selbuy'})
        items = info.find_all('tr', attrs={'class': True})
        for x in items:
            try:
                y = x.find_all('td')
                bus_num = y[0].get_text().strip()
                full_price = y[6].get_text().strip()
                left_tickets = y[10].get_text().strip()
                line_id_args = {
                    's_city_name': line.s_city_name,
                    'd_city_name': line.d_city_name,
                    'bus_num': bus_num,
                    'crawl_source': line.crawl_source,
                    'drv_datetime': line.drv_datetime,
                }
                line_id = md5("%(s_city_name)s-%(d_city_name)s-%(drv_datetime)s-%(bus_num)s-%(crawl_source)s" % line_id_args)
                if line_id in t:
                    t[line_id].update(**{"left_tickets": left_tickets, 'full_price': full_price, "refresh_datetime": now})
                if line_id == line.line_id and int(left_tickets):
                    update_attrs = {"left_tickets": left_tickets, 'full_price': full_price, "refresh_datetime": now}
            except:
                pass

        result_info = {}
        if not update_attrs:
            result_info.update(result_msg="no line info", update_attrs={
                               "left_tickets": 0, "refresh_datetime": now})
        else:
            result_info.update(result_msg="ok", update_attrs=update_attrs)
        return result_info

    def get_pay_page(self, order, valid_code="", session=None, pay_channel="alipay", **kwargs):
        rebot = order.get_lock_rebot()
        is_login = rebot.test_login_status()

        # 登录验证码
        # rebot_log.info(is_login)
        if not is_login:
            for x in xrange(3):
                v = vcode_glcx()
                if not v:
                    continue
                valid_code = v[0]
                cookies = v[1]
                params = {
                    "userId": rebot.telephone,
                    "password": rebot.password,
                    "rand": valid_code,
                    'remmber': 'on',
                }
                headers = {
                    "User-Agent": rebot.user_agent,
                    "Content-Type": "application/x-www-form-urlencoded",
                }
                url = 'http://www.0000369.cn/login!login.action'
                r = requests.post(url,
                                  data=urllib.urlencode(params),
                                  headers=headers,
                                  # allow_redirects=False,
                                  cookies=cookies)
                soup = bs(r.content, 'lxml')
                info = soup.find('a', attrs={'onclick': 'tomyorder();'}).get_text()
                if re.findall(r'\d+', info)[0]:
                    ncookies = {
                        'JSESSIONID': dict(cookies)['JSESSIONID'],
                        'remm': 'true',
                        'user': rebot.telephone,
                        'pass': rebot.password,
                    }
                    # rebot_log.info(re.findall(r'\d+', info)[0])
                    rebot.modify(cookies=json.dumps(ncookies))
                    break

        is_login = is_login or rebot.test_login_status()
        if is_login:
            if order.status in [STATUS_LOCK_RETRY, STATUS_WAITING_LOCK]:
                self.lock_ticket(order)

            if order.status == STATUS_WAITING_ISSUE:
                cookies = json.loads(rebot.cookies)
                headers = {
                    "User-Agent": rebot.user_agent,
                    "Content-Type": "application/x-www-form-urlencoded",
                    'Referer': 'http://www.0000369.cn/order!topay.action',
                }
                # v = vcode_glcx(cookies)
                # url = 'http://www.0000369.cn/buytks!checkRand.action?rand=%s' % v[0]
                # r = requests.get(url, headers=headers, cookies=cookies)
                # rebot_log.info(r.content)
                pay_url = 'http://www.0000369.cn/order!toAfformOrder.action'
                data = order.extra_info
                r = requests.post(pay_url, data=urllib.urlencode(data), headers=headers, cookies=cookies, allow_redirects=False)
                soup = bs(r.content, 'lxml')
                # rebot_log.info(soup)
                trade_no = soup.find_all('label')[0].get_text()
                pay_money = float(soup.find_all('label')[1].get_text())
                if order.pay_money != pay_money or order.pay_order_no != trade_no:
                    order.modify(pay_money=pay_money, pay_order_no=trade_no, pay_channel='yh')
                return {"flag": "html", "content": r.content.replace('src="/', 'src="http://www.0000369.cn/')}
