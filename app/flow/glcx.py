# coding=utf-8

import requests
import json
import urllib

import datetime
import random
from bs4 import BeautifulSoup as bs

from app.constants import *
from datetime import datetime as dte
from app.flow.base import Flow as BaseFlow
from app.models import Line, GlcxWebRebot
from app.utils import md5, vcode_glcx
from app import order_log


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
        # pa = urllib.quote(pa.encode('utf-8'), safe='=&+')
        # r = requests.post(url, headers=headers, cookies=cookies, data=pa)
        # soup = bs(r.content, 'lxml')
        # info = soup.find('div', attrs={'class': 'buy'})
        v = vcode_glcx(cookies)
        url = 'http://www.0000369.cn/buytks!toAffirm.action'
        pre = 'insuranceValue=2&'
        # rider = list(order.riders)
        pk = len(order.riders)
        # for x in rider:
        #     if uid == x['id_number']:
        #         rider.remove(x)
        tmp = ''
        for x in order.riders:
            tmp += 'name=%s&idcard=%s&tel=%s&tkstype=0&\
            insurance=0&' %(x['name'], x['id_number'], tel)

        suf = 'rand=%s&bliid=%s+&sendTime=&stationId=%s&\
        bliidSendDatetime=%s+%s&arrivalPortID=%s&\
        customName=%s&customTelephone=%s&customIDCardNo=%s\
        &customAddress=&ticketDate=%s&startNo=%s&CanSellNum=%s\
        &ticketPrice=%s' %(v[0], line.bus_num, line.s_sta_id, line.drv_date,
            line.drv_time, line.d_sta_id, rebot.telephone, rebot.telephone, rebot.userid, line.drv_date,
            line.extra_info['startNo'], line.left_tickets, line.full_price)

        pa = pre + tmp + suf
        pa = ''.join(pa.split())
        pa = urllib.quote(pa.encode('utf-8'), safe='=&+')
        r = requests.post(url, headers=headers, cookies=cookies, data=pa)
        soup = bs(r.content, 'lxml')
        try:
            sn = soup.find('input', attrs={'id': 'dealOrder'}).get('value', '')
        except:
            sn = ''
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
        else:
            try:
                errmsg = soup.find('ul', attrs={'class': 'errorMessage'}).get_text().strip()
            except:
                errmsg = ''
            if '座号不足' in errmsg or '票价非法更改' in errmsg:
                self.close_line(order.line)
                lock_result.update({
                    'result_code': 0,
                    "result_reason": errmsg,
                })
                return lock_result
            if errmsg:
                order_log.info("[lock-fail] order: %s %s", order.order_no, errmsg)
                lock_result.update({
                    'result_code': 2,
                    "result_reason": errmsg,
                })
                return lock_result
            errmsg = soup.title.get_text()
            lock_result.update({
                'result_code': 2,
                "result_reason": errmsg,
            })
            return lock_result

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
        info = soup.find('table', attrs={'id': 'selorder'}).find_all('tr', attrs={'class': True})
        amount = 0
        for x in info:
            try:
                sn1 = x.find_all('td')[1].get_text().strip()
                if sn == sn1:
                    amount += 1
                    state = x.find_all('td')[6].get_text().strip()
            except:
                pass
        if amount == len(order.riders):
            return {
                "state": state,
                "pick_no": sn,
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
        if '失败' in state:
            result_info.update({
                "result_code": 2,
                "result_msg": state,
            })
        elif '已付款' == state:
            no,  raw_order = ret['pick_no'], ret['raw_order']
            dx_info = {
                "time": order.drv_datetime.strftime("%Y-%m-%d %H:%M"),
                "start": order.line.s_sta_name,
                "end": order.line.d_sta_name,
                "no": no,
                'raw_order': raw_order,
            }
            dx_tmpl = DUAN_XIN_TEMPL[SOURCE_GLCX]
            code_list = [no]
            msg_list = [dx_tmpl % dx_info]
            result_info.update({
                "result_code": 1,
                "result_msg": state,
                "pick_code_list": code_list,
                "pick_msg_list": msg_list,
            })
        return result_info

    def do_refresh_line(self, line):
        now = dte.now()
        result_info = {}
        data = {
            'stationId': line.s_sta_id,
            'portId': line.d_sta_id,
            'startTime': line.drv_date,
        }
        rebot = GlcxWebRebot.get_one()
        headers = {
            "User-Agent": random.choice(BROWSER_USER_AGENT),
            'Content-Type': 'application/x-www-form-urlencoded',
            'X-Requested-With': 'XMLHttpRequest',
        }
        url = 'http://www.0000369.cn/buytks!searchtks.action'
        try:
            r = rebot.http_post(url, headers=headers, data=urllib.urlencode(data))
            soup = bs(r.content, 'lxml')
        except:
            result_info.update(result_msg="exception_ok", update_attrs={"left_tickets": 5, "refresh_datetime": now})
            return result_info

        ft = Line.objects.filter(s_city_name=line.s_city_name, d_city_name=line.d_city_name, drv_date=line.drv_date)
        db_lines = {x.line_id: x for x in ft}

        update_attrs = {}
        for tr_o in soup.select("table #selbuy"):
            td_lst = tr_o.find_all('td')
            if len(td_lst) < 2:
                continue
            index_tr = lambda idx: td_lst[idx].text.strip().decode("utf-8")
            full_price=float(index_tr(6))
            left_tickets=int(index_tr(10))
            drv_date, drv_time = line.drv_date, index_tr(1)
            if u"流水" in drv_time:
                continue
            drv_datetime=dte.strptime("%s %s" % (drv_date, drv_time), "%Y-%m-%d %H:%M")
            line_id_args = {
                's_city_name': line.s_city_name,
                'd_city_name': line.d_city_name,
                'crawl_source': line.crawl_source,
                's_sta_name': line.s_sta_name,
                'd_sta_name': line.d_sta_name,
                'drv_datetime': drv_datetime,
            }
            line_id = md5("%(s_city_name)s-%(d_city_name)s-%(drv_datetime)s-%(s_sta_name)s-%(d_sta_name)s-%(crawl_source)s" % line_id_args)
            if line_id in db_lines:
                db_lines[line_id].update(**{"left_tickets": left_tickets, 'full_price': full_price, "refresh_datetime": now})
            if line_id == line.line_id:
                update_attrs = {"left_tickets": left_tickets, 'full_price': full_price, "refresh_datetime": now}

        if not update_attrs:
            result_info.update(result_msg="no line info", update_attrs={"left_tickets": 0, "refresh_datetime": now})
        else:
            result_info.update(result_msg="ok", update_attrs=update_attrs)
        return result_info

    def get_pay_page(self, order, valid_code="", session=None, pay_channel="alipay", **kwargs):
        rebot = order.get_lock_rebot()
        is_login = rebot.test_login_status()

        # 登录验证码
        if not is_login:
            for x in xrange(3):
                if rebot.login() == "OK":
                    is_login = True
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
                pay_url = 'http://www.0000369.cn/order!toAfformOrder.action'
                data = order.extra_info
                r = requests.post(pay_url, data=urllib.urlencode(data), headers=headers, cookies=cookies, allow_redirects=False)
                soup = bs(r.content, 'lxml')
                content = r.content.replace('src="/', 'src="http://www.0000369.cn/').replace('href="/', 'href="http://www.0000369.cn/')
                trade_no = soup.find_all('label')[0].get_text()
                pay_money = float(soup.find_all('label')[1].get_text())
                if order.pay_money != pay_money or order.pay_order_no != trade_no:
                    order.modify(pay_money=pay_money, pay_order_no=trade_no, pay_channel='yh')
                return {"flag": "html", "content": content}
