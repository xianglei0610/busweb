# coding=utf-8

import requests
import re
import urllib
import datetime
import random

from bs4 import BeautifulSoup as bs
from app.proxy import get_redis
from app.constants import *
from datetime import datetime as dte
from app.flow.base import Flow as BaseFlow
from app.models import Line,Sd365WebRebot
from app.utils import md5
from app import order_log


class Flow(BaseFlow):
    name = 'sd365'
    requests.adapters.DEFAULT_RETRIES = 5  # fix Max retries exceeded with url

    # 锁票
    def get_proxy(self):
        rds = get_redis("default")
        ipstr = rds.srandmember(RK_PROXY_IP_SD365)
        ip = {'http': 'http://%s' %ipstr}
        return ip

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
        proxies = self.get_proxy()
        line = order.line
        pk = len(order.riders)
        ua = random.choice(BROWSER_USER_AGENT)
        headers = {'User-Agent': ua}
        headers['Content-Type'] = 'application/x-www-form-urlencoded'
        headers['Referer'] = 'http://www.36565.cn/?c=tkt3&a=confirming'
        extra = line.extra_info
        for x, y in extra.items():
            extra[x] = y.encode('utf-8')
        uname = order.contact_info['name']
        tel = order.contact_info['telephone']
        uid = order.contact_info['id_number']
        tpass = random.randint(111111, 999999)
        shopid = extra['sid']
        port = extra['dpid']
        lline = extra['l']
        pre = 'member_name=%s&tktphone=%s&\
        ticketpass=%s&paytype=3&shopid=%s&\
        port=%s&line=%s&tdate=%s+%s&offer=0&\
        offer2=0&tkttype=0&' %(uname, tel, tpass, \
            shopid, port, lline, line['drv_date'], line['drv_time'])
        rider = list(order.riders)
        #for x in rider:
        #     if uid == x['id_number']:
        #         rider.remove(x)
        tmp = ''
        if 1:
            for i, x in enumerate(rider):
                i += 1
                tmp += 'savefriend[]=%s&tktname[]=%s&papertype[]=0&paperno[]=%s&offertype[]=&price[]=%s&\
                insureproduct[]=1&insurenum[]=0&insurefee[]=0&chargefee[]=0&' %(i, x['name'].encode('utf-8'), x['id_number'], line['full_price'])

        pa = pre + tmp + '&bankname=ZHIFUBAO'
        pa = ''.join(pa.split())
        pa = urllib.quote(pa.encode('utf-8'), safe='=&+')
        url = 'http://www.36565.cn/?c=tkt3&a=payt'
        try:
            r = requests.post(url, headers=headers, data=pa, allow_redirects=False, timeout=64, proxies=proxies)
            location = urllib.unquote(r.headers.get('location', ''))
            sn = location.split(',')[3]
        except:
            sn = ''
            location = ''
        # fail_reason = ''
        # if not sn:
        #     ndata = {
        #         'sid': extra['sid'],
        #         'l': extra['l'],
        #         'dpid': extra['dpid'],
        #         't': extra['t'],
        #     }
        #     nurl = 'http://www.36565.cn/?c=tkt3&a=confirm&' + urllib.urlencode(ndata)
        #     r = requests.get(nurl, headers=headers, proxies=proxies)
        #     urlstr = urllib.unquote(r.url.decode('gbk').encode('utf-8'))
        #     if '该班次价格不存在' in urlstr:
        #         order_log.info("[lock-fail] order: %s %s", order.order_no, urlstr)
        #         self.close_line(line)
        #         fail_reason = u'服务器异常'
        if 'mapi.alipay.com' in location and sn:
            expire_time = dte.now() + datetime.timedelta(seconds=15 * 60)
            if order.extra_info.get('retry_count', ''):
                order.modify(extra_info={})
            order.modify(extra_info={'pay_url': location, 'sn': sn, 'pcode': tpass})
            lock_result.update({
                'result_code': 1,
                'raw_order_no': sn,
                "expire_datetime": expire_time,
                "source_account": '',
                'pay_money': 0,
            })
            return lock_result
        # elif fail_reason:
        #     lock_result.update({
        #         'result_code': 0,
        #         "result_reason": fail_reason,
        #     })
        #     return lock_result
        elif '不售票' in location or '票务错误' in location or '超出人数限制' in location or '票源不足' in location:
            order_log.info("[lock-fail] order: %s %s", order.order_no, location)
            self.close_line(line)
            errlst = re.findall(r'message=(\S+)&url', location)
            errmsg = unicode(errlst and errlst[0] or "")
            if errmsg:
                lock_result.update({
                    'result_code': 0,
                    "result_reason": errmsg,
                })
                return lock_result
            errlst = re.findall(r'message=(\S+)', location)
            errmsg = unicode(errlst and errlst[0] or "")
            lock_result.update({
                'result_code': 0,
                "result_reason": errmsg,
            })
            return lock_result
        else:
            retry_count = order.extra_info.get('retry_count', '')
            if not retry_count:
                retry_count = 1
            if retry_count > 15:
                lock_result.update({
                    'result_code': 0,
                    "result_reason": '无法下单',
                })
                return lock_result
            retry_count += 1
            order.modify(extra_info={'retry_count': retry_count})
            lock_result.update({
                'result_code': 2,
                "result_reason": location,
            })
            return lock_result

    def send_order_request(self, order):
        ua = random.choice(BROWSER_USER_AGENT)
        proxies = self.get_proxy()
        headers = {'User-Agent': ua}
        headers['Content-Type'] = 'application/x-www-form-urlencoded'
        url = 'http://www.36565.cn/?c=order2&a=index'
        for y in order.riders:
            data = {'eport': y['id_number']}
            try:
                r = requests.post(url, headers=headers, data=data, proxies=proxies)
                soup = bs(r.content, 'lxml')
                info = soup.find_all('div', attrs={'class': 'userinfoff'})[1].find_all('div', attrs={'class': 'billinfo'})
            except:
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
        now = dte.now()
        headers = {"User-Agent": random.choice(BROWSER_USER_AGENT),}
        rebot = Sd365WebRebot.get_one()
        url = 'http://www.36565.cn/?c=tkt3&a=search&fromid=&from={0}&toid=&to={1}&date={2}&time=0#'.format(line.s_city_name, line.d_city_name, line.drv_date)
        try:
            r = rebot.http_get(url, headers=headers)
            code = r.content.split('code:')[-1].split()[0].split('"')[1]
            soup = bs(r.content, 'lxml')
            info = soup.find_all('input', attrs={'class': 'filertctrl', 'name': 'siids'})
        except:
            result_info = {}
            result_info.update(result_msg="exception_ok1", update_attrs={"left_tickets": 5, "refresh_datetime": now})
            return result_info
        sids = ",".join([x["value"] for x in info])
        data = {
            'a': 'getlinebysearch',
            'c': 'tkt3',
            'toid': '',
            'type': '0',
            'code': code,
            'date': line.drv_date,
            'sids': sids,
            'to': line.d_city_name,
        }
        lasturl = 'http://www.36565.cn/?' + urllib.urlencode(data)
        for y in xrange(1):
            try:
                r = rebot.http_get(lasturl, headers=headers)
                soup = r.json()
            except:
                result_info = {}
                result_info.update(result_msg="exception_ok2", update_attrs={"left_tickets": 5, "refresh_datetime": now})
                return result_info

            update_attrs = {}
            ft = Line.objects.filter(s_city_name=line.s_city_name,d_city_name=line.d_city_name, drv_date=line.drv_date)
            t = {x.line_id: x for x in ft}
            update_attrs = {}
            for x in soup:
                drv_date = x['bpnDate']
                drv_time = x['bpnSendTime']
                left_tickets = x['bpnLeftNum']
                full_price = x['prcPrice']
                drv_datetime = dte.strptime("%s %s" % (drv_date, drv_time), "%Y-%m-%d %H:%M")
                line_id_args = {
                    "s_city_name": line.s_city_name,
                    "d_city_name": line.d_city_name,
                    "s_sta_name": unicode(x["shifazhan"]),
                    "d_sta_name": unicode(x["prtName"]),
                    "crawl_source": line.crawl_source,
                    "drv_datetime": drv_datetime,
                }
                line_id = md5("%(s_city_name)s-%(d_city_name)s-%(drv_datetime)s-%(s_sta_name)s-%(d_sta_name)s-%(crawl_source)s" % line_id_args)
                if line_id in t:
                    t[line_id].update(**{"left_tickets": left_tickets, "refresh_datetime": now, 'full_price': full_price})
                if line_id == line.line_id and int(left_tickets):
                    update_attrs = {"left_tickets": left_tickets, "refresh_datetime": now, 'full_price': full_price}

            result_info = {}
            if not update_attrs:
                result_info.update(result_msg="no line info", update_attrs={"left_tickets": 0, "refresh_datetime": now})
            else:
                result_info.update(result_msg="ok", update_attrs=update_attrs)
            return result_info

    def get_pay_page(self, order, valid_code="", session=None, pay_channel="alipay", **kwargs):

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
                    order.modify(pay_order_no=no, pay_money=pay, pay_channel='alipay')
                return {"flag": "url", "content": pay_url}
        if order.status in [STATUS_LOCK_RETRY, STATUS_WAITING_LOCK]:
            self.lock_ticket(order)
        order.reload()
        if order.status == STATUS_WAITING_ISSUE:
            return _get_page()
