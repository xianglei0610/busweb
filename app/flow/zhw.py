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
from app.models import Line, ZhwWebRebot
from app.utils import md5, vcode_zhw
from app import rebot_log
from requests.utils import cookiejar_from_dict, dict_from_cookiejar


class Flow(BaseFlow):
    name = 'zhw'

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
        pk = len(order.riders)
        headers = {'User-Agent': rebot.user_agent}
        headers['Content-Type'] = 'application/x-www-form-urlencoded; charset=UTF-8'
        headers['Host'] = 'www.zhwsbs.gov.cn:9013'
        extra = line.extra_info
        for x, y in extra.items():
            extra[x] = y.encode('utf-8')
        data = {
            'we': '1',
            'txtSchLocalCode': extra['txtSchLocalCode'],
            'txtSchStationName': extra['txtSchStationName'],
            'txtSchWaitStCode': extra['txtSchWaitStCode'],
            'txtSchDstNode': extra['txtSchDstNode'],
            'txtSchWaitingRoom': '',
            'txtSchDate': line['drv_date'],
            'txtSchTime': line['drv_time'],
            'txtSchWaitStName': line['s_sta_name'],
            'txtSchDstNodeName': line['d_sta_name'],
            'txtSchPrice': line['full_price'],
            'txtSchTicketCount': line['left_tickets'],
            'txtNumberTicket': '1',
            'txtSginData': extra['txtSginData'],
            'ctm': extra['ctm'],
        }
        url = 'http://www.zhwsbs.gov.cn:9013/shfw/zaotsTicket/payCtky2.xhtml'
        r = requests.post(url, headers=headers, data=data)
        soup = bs(r.content, 'lxml')
        data = {
            'txtSchLocalCode': extra['txtSchLocalCode'],
            'txtSchStationName': extra['txtSchStationName'],
            'txtSchWaitStCode': extra['txtSchWaitStCode'],
            'txtSchDstNode': extra['txtSchDstNode'],
            'txtSchWaitingRoom': '',
            'txtSchDate': line['drv_date'],
            'txtSchTime': line['drv_time'],
            'txtSchWaitStName': line['s_sta_name'],
            'txtSchDstNodeName': line['d_sta_name'],
            'txtSchPrice': line['full_price'],
            'txtSchTicketCount': line['left_tickets'],
            'txtNumber': pk,
            'txtName': order.contact_info['name'],
            'txtPhone': order.contact_info['telephone'],
            'txtCustCerType': '居民身份证',
            'txtCustCerNo': order.contact_info['id_number'],
            'txtEmail': '',
            'txtAddress': '',
            'txtRemark': '',
            'zaotsShopcartId': '',
        }
        headers['X-Requested-With'] = 'XMLHttpRequest'
        headers['Referer'] = 'http://www.zhwsbs.gov.cn:9013/shfw/zaotsTicket/payCtky2.xhtml'
        url = 'http://www.zhwsbs.gov.cn:9013/shfw/zaotsTicket/saveTicket.xhtml'
        r = requests.post(url, headers=headers, cookies=r.cookies, data=data)
        cks = r.cookies
        soup = json.loads(r.content).get('info', '')
        orderUUID = soup.split('=')[-1]
        if '创建订单成功' in soup and orderUUID:
            expire_time = dte.now() + datetime.timedelta(seconds=15 * 60)
            cookies = {}
            for x, y in cks.items():
                cookies[x] = y
            order.modify(extra_info={'cookies': json.dumps(cookies), 'orderUUID': orderUUID})
            # order.modify(pay_money=line['full_price'] * pk, pay_order_no=orderUUID)
            lock_result.update({
                'result_code': 1,
                'raw_order_no': orderUUID,
                "expire_datetime": expire_time,
                "source_account": rebot.telephone,
                'pay_money': 0,
            })
            return lock_result
        else:
            lock_result.update({
                'result_code': 2,
                "lock_info": {"fail_reason": soup.split(',')[0]}
            })
            return lock_result

    def send_order_request(self, order):
        rebot = order.get_lock_rebot()
        url = 'http://www.zhwsbs.gov.cn:9013/shfw/zaotsOrders/findOrderById.xhtml?oid=' + order.extra_info.get('orderUUID')
        headers = {
            "User-Agent": rebot.user_agent,
        }
        r = requests.get(url, headers=headers)
        soup = bs(r.content, 'lxml')
        info = soup.find('table', attrs={'class': 'p_detail_table fl'}).find_all('tr')
        pcode = info[1].find_all('td')[1].get_text().strip()
        pcode = re.findall(r'\d*', pcode)[0]
        state = info[2].find_all('td')[-1].get_text().strip()
        return {
            "state": state,
            "pick_no": pcode,
            "pick_code": pcode,
            "pick_site": '',
            'raw_order': order.extra_info.get('orderUUID'),
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
        pcode = ret['pick_code']
        rebot_log.info(ret)
        rebot_log.info(state)
        if '失败' in state:
            result_info.update({
                "result_code": 2,
                "result_msg": state,
            })
        elif '交易成功' in state and pcode:
            dx_info = {
                "time": order.drv_datetime.strftime("%Y-%m-%d %H:%M"),
                "start": order.line.s_sta_name,
                "end": order.line.d_sta_name,
                "pcode": pcode,
                'person': '取票人',
            }
            dx_tmpl = DUAN_XIN_TEMPL[SOURCE_ZHW]
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
        url = 'http://www.zhwsbs.gov.cn:9013/shfw/zaotsTicket/pageLists.xhtml'
        ua = random.choice(BROWSER_USER_AGENT)
        headers = {
            "User-Agent": ua,
            "Content-Type": "application/x-www-form-urlencoded",
            'Referer': 'http://www.zhwsbs.gov.cn:9013/shfw/zaotsTicket/pageLists.xhtml',
        }
        d = {
            u'香洲长途站': 'C1K001-102017',
            u'上冲站': 'C1K027-102018',
            u'南溪站': 'C1K013-102019',
            u'拱北通大站': 'C1K030-102023',
            u'斗门站': 'C2K003-102027',
            u'井岸站': 'C2K001-102028',
            u'红旗站': 'C1K006-102030',
            u'三灶站': 'C1K004-102031',
            u'平沙站': 'C1K007-102032',
            u'南水站': 'C1K008-102033',
            u'唐家站': 'TJZ001-102020',
            u'金鼎站': 'JDZ001-102021',
            u'拱北票务中心': 'GBPW01-102024',
            u'西埔站': 'XPZ001-102029',
        }
        result_info = {}
        now = dte.now()
        for x in xrange(1):
            rebot = ZhwWebRebot.objects.filter(telephone='15338702029').first()
            if rebot:
                code = rebot.code
                cookies = json.loads(rebot.cookies)
                cookies = cookiejar_from_dict(cookies)
            else:
                v = vcode_zhw()
                code = v[0]
                cookies = v[1]
            data = {
                'SchDate': line['drv_date'],
                'SchTime': '',
                'checkCode': code,
                'StartStation': d.get(line['s_sta_name'], ''),
                'SchDstNodeName': line['d_city_name'],
            }
            r = requests.post(url, headers=headers, cookies=cookies, data=data)
            soup = bs(r.content, 'lxml')
            info = soup.find('table', attrs={'id': 'changecolor'})
            if '验证码' in info.get_text():
                # vcookies.remove({'cookies': {'$exists': True}})
                rebot.modify(cookies={}, code='')
                continue
            else:
                cookies = dict(r.cookies)
                cks = {'JSESSIONID1_ZH_DY_SHFW': cookies.values()[0]}
                rebot.modify(cookies=json.dumps(cks), code=code)
            items = info.find_all('tr', attrs={'id': True})
            update_attrs = {}
            ft = Line.objects.filter(s_city_name=line.s_city_name,
                                     d_city_name=line.d_city_name, drv_date=line.drv_date)
            t = {x.line_id: x for x in ft}
            update_attrs = {}
            for x in items:
                try:
                    y = x.find_all('td')
                    sts = x.find('input', attrs={'class': 'g_table_btn'}).get('value', '')
                    drv_date = y[0].get_text().strip()
                    drv_time = y[1].get_text().strip()
                    s_sta_name = y[2].get_text().strip()
                    d_sta_name = y[3].get_text().strip()
                    left_tickets = y[5].get_text().strip()
                    # vehicle_type = y[6].get_text().strip()
                    drv_datetime = dte.strptime("%s %s" % (
                        drv_date, drv_time), "%Y-%m-%d %H:%M")
                    line_id_args = {
                        "s_city_name": line.s_city_name,
                        "d_city_name": line.d_city_name,
                        "s_sta_name": s_sta_name,
                        "d_sta_name": d_sta_name,
                        "crawl_source": line.crawl_source,
                        "drv_datetime": drv_datetime,
                    }
                    line_id = md5("%(s_city_name)s-%(d_city_name)s-%(drv_datetime)s-%(s_sta_name)s-%(d_sta_name)s-%(crawl_source)s" % line_id_args)
                    if line_id in t:
                        t[line_id].update(**{"left_tickets": left_tickets, "refresh_datetime": now})
                    if line_id == line.line_id and sts in [u'不在服务时间', u'立即购买']:
                        update_attrs = {"left_tickets": left_tickets, "refresh_datetime": now}
                except Exception, e:
                    print e
                    pass

            if not update_attrs:
                result_info.update(result_msg="no line info", update_attrs={
                                   "left_tickets": 0, "refresh_datetime": now})
            else:
                result_info.update(result_msg="ok", update_attrs=update_attrs)
            return result_info
        else:
            result_info.update(result_msg="exception_ok", update_attrs={"left_tickets": 5, "refresh_datetime": now})
            return result_info

    def get_pay_page(self, order, valid_code="", session=None, pay_channel="alipay", **kwargs):
        rebot = order.get_lock_rebot()

        # 获取alipay付款界面
        def _get_page(rebot):
            if order.status == STATUS_WAITING_ISSUE:
                cookies = json.loads(order.extra_info.get('cookies'))
                # orderUUID = order.extra_info.get('orderUUID')
                ua = random.choice(BROWSER_USER_AGENT)
                headers = {
                    "User-Agent": ua,
                    "Content-Type": "application/x-www-form-urlencoded"
                }
                url = 'http://www.zhwsbs.gov.cn:9013/jsps/shfw2/pay_ctky_orderPost.jsp'
                r = requests.get(url, headers=headers, cookies=cookies)
                soup = bs(r.content, 'lxml')
                info = soup.find('form').find_all('input', attrs={'name': True})
                data = {}
                for x in info:
                    data[x['name']] = x['value']
                OrderUUID = data['OrderUUID']
                pay_money = float(data['SchPrice'])*int(data["Number"])
                if order.pay_money != pay_money or order.pay_order_no != OrderUUID:
                    order.modify(pay_money=pay_money, pay_order_no=OrderUUID,pay_channel='yh')
                return {"flag": "html", "content": r.content}
        if order.status in [STATUS_LOCK_RETRY, STATUS_WAITING_LOCK]:
            self.lock_ticket(order)

        if order.status == STATUS_WAITING_ISSUE:
            return _get_page(rebot)
