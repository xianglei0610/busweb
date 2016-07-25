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

from app.proxy import get_redis
from app.constants import *
from datetime import datetime as dte
from app.flow.base import Flow as BaseFlow
from app.models import Line
from app.utils import md5
from app import rebot_log, order_log
import random


class Flow(BaseFlow):
    name = 'sd365'

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
        # tpass = '200101'
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
        # rebot_log.info(pa)
        pa = urllib.quote(pa.encode('utf-8'), safe='=&+')
        url = 'http://www.36565.cn/?c=tkt3&a=payt'
        r = requests.post(url, headers=headers, data=pa, allow_redirects=False, timeout=256, proxies=proxies)
        location = urllib.unquote(r.headers.get('location', ''))
        # rebot_log.info(location)
        try:
            sn = location.split(',')[3]
        except:
            sn = ''
        fail_reason = ''
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
            # cookies = {}
            # for x, y in cks.items():
            #     cookies[x] = y
            order.modify(extra_info={'pay_url': location, 'sn': sn, 'pcode': tpass})
            lock_result.update({
                'result_code': 1,
                'raw_order_no': sn,
                "expire_datetime": expire_time,
                "source_account": '',
                'pay_money': 0,
            })
            return lock_result
        elif fail_reason:
            lock_result.update({
                'result_code': 0,
                "result_reason": fail_reason,
            })
            return lock_result
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
            r = requests.post(url, headers=headers, data=data, proxies=proxies)
            soup = bs(r.content, 'lxml')
            info = soup.find_all('div', attrs={'class': 'userinfoff'})[1].find_all('div', attrs={'class': 'billinfo'})
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
        # rebot_log.info(ret)
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
            # rebot_log.info(result_info)
        return result_info

    # 线路刷新, java接口调用
    def do_refresh_line(self, line):
        ua = random.choice(BROWSER_USER_AGENT)
        now = dte.now()
        headers = {
            "User-Agent": ua,
            'Content-Type': 'application/x-www-form-urlencoded',
        }
        # rebot_log.info(line['s_city_name'])
        extra = line.extra_info
        ndata = {
            'sid': extra['sid'],
            'l': extra['l'],
            'dpid': extra['dpid'],
            't': extra['t'],
        }
        nurl = 'http://www.36565.cn/?c=tkt3&a=confirm&' + urllib.urlencode(ndata)
        proxies = self.get_proxy()
        r = requests.get(nurl, headers=headers, proxies=proxies)
        urlstr = urllib.unquote(r.url.decode('gbk').encode('utf-8'))
        if '该班次价格不存在' in urlstr or '发车前2小时不售票' in urlstr:
            result_info = {
                'result_msg' :"no line info",
                'update_attrs': {"left_tickets": 0, "refresh_datetime": now}
            }
            return result_info
        # rebot_log.info(nurl)
        for x in xrange(1):
            url = 'http://www.36565.cn/?c=tkt3&a=search&fromid=&from={0}&toid=&to={1}&date={2}&time=0#'.format(line.s_city_name, line.d_city_name, line.drv_date)
            r = requests.get(url, headers=headers, proxies=proxies)
            try:
                code = r.content.split('code:')[-1].split()[0].split('"')[1]
            except:
                code = ''
            soup = bs(r.content, 'lxml')
            info = soup.find_all('input', attrs={'class': 'filertctrl', 'name': 'siids'})
            sids = ''
            for x in info:
                sids += x['value'] + ','
            # rebot_log.info(sids + code)
            if not sids and not code:
                continue
            data = {
                'a': 'getlinebysearch',
                'c': 'tkt3',
                'toid': '',
                'type': '0',
                'code': code,
                'date': line.drv_date,
                'sids': sids[:-1],
                'to': line.d_city_name,
            }
            lasturl = 'http://www.36565.cn/?' + urllib.urlencode(data)
            # rebot_log.info(lasturl)
            for y in xrange(1):
                r = requests.get(lasturl, proxies=proxies)
                try:
                    soup = r.json()
                except:
                    result_info = {}
                    result_info.update(result_msg="exception_ok", update_attrs={"left_tickets": 5, "refresh_datetime": now})
                    return result_info
                tpk = now + datetime.timedelta(hours=2.2)
                update_attrs = {}
                ft = Line.objects.filter(s_city_name=line.s_city_name,
                                         d_city_name=line.d_city_name, drv_date=line.drv_date)
                t = {x.line_id: x for x in ft}
                # rebot_log.info(t)
                # rebot_log.info(len(t))
                update_attrs = {}
                for x in soup:
                    try:
                        drv_date = x['bpnDate']
                        drv_time = x['bpnSendTime']
                        left_tickets = x['bpnLeftNum']
                        full_price = x['prcPrice']
                        bus_num = x['bliID']
                        drv_datetime = dte.strptime("%s %s" % (
                            drv_date, drv_time), "%Y-%m-%d %H:%M")
                        line_id_args = {
                            "s_city_name": line.s_city_name,
                            "d_city_name": line.d_city_name,
                            "crawl_source": line.crawl_source,
                            "drv_datetime": drv_datetime,
                            'bus_num': bus_num,
                        }
                        line_id = md5("%(s_city_name)s-%(d_city_name)s-%(drv_datetime)s-%(bus_num)s-%(crawl_source)s" % line_id_args)
                        # rebot_log.info(line_id)
                        # rebot_log.info(left_tickets)
                        if line_id in t:
                            t[line_id].update(**{"left_tickets": left_tickets, "refresh_datetime": now, 'full_price': full_price})
                        if line_id == line.line_id and int(left_tickets) and tpk < line.drv_datetime:
                            update_attrs = {"left_tickets": left_tickets, "refresh_datetime": now, 'full_price': full_price}
                    except:
                        pass

                result_info = {}
                if not update_attrs:
                    result_info.update(result_msg="no line info", update_attrs={
                                       "left_tickets": 0, "refresh_datetime": now})
                else:
                    result_info.update(result_msg="ok", update_attrs=update_attrs)
                return result_info
        else:
            result_info = {}
            result_info.update(result_msg="exception_ok", update_attrs={"left_tickets": 5, "refresh_datetime": now})
            return result_info

    def get_pay_page(self, order, valid_code="", session=None, pay_channel="alipay", **kwargs):

        # 获取alipay付款界面
        def _get_page():
            if order.status == STATUS_WAITING_ISSUE:
                pay_url = order.extra_info.get('pay_url')
                # rebot_log.info(pay_url)
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
