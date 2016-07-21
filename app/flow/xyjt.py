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
from selenium import webdriver
from selenium.webdriver.common.desired_capabilities import DesiredCapabilities
# from cchardet import detect
# import ipdb


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
        rebot = order.get_lock_rebot()
        line = order.line
        pk = len(order.riders)
        headers = {'User-Agent': rebot.user_agent}
        headers['Content-Type'] = 'application/x-www-form-urlencoded'
        headers['Host'] = 'order.xuyunjt.com'
        data = line.extra_info
        for x, y in data.items():
            data[x] = y.encode('utf-8')
        url = 'http://order.xuyunjt.com/wsdgnetorder.aspx?' + \
            urllib.urlencode(data)
        r = requests.get(url, headers=headers, data=urllib.urlencode(data))
        soup = bs(r.content, 'lxml')
        state = soup.find(
            'input', attrs={'name': '__VIEWSTATE', 'id': '__VIEWSTATE'}).get('value', '')
        validation = soup.find('input', attrs={
            'name': '__EVENTVALIDATION', 'id': '__EVENTVALIDATION'}).get('value', '')
        data = {}
        data = {
            '__EVENTTARGET': '',
            '__EVENTARGUMENT': '',
            '__VIEWSTATE': state,
            '__EVENTVALIDATION': validation,
            'ctl00$ContentPlaceHolder1$txtjp_price': line.half_price,
            'ctl00$ContentPlaceHolder1$txttp_price': line.half_price,
            'ctl00$ContentPlaceHolder1$txtqp_price': line.full_price * pk,
            'ctl00$ContentPlaceHolder1$txtoffer_price': '0',
            'ctl00$ContentPlaceHolder1$ddlqp': pk,
            'ctl00$ContentPlaceHolder1$ddljp': '0',
            'ctl00$ContentPlaceHolder1$ddltp': '0',
            'ctl00$ContentPlaceHolder1$txttotal': pk,
            'ctl00$ContentPlaceHolder1$txttotalprice': line.full_price * pk,
            'ctl00$ContentPlaceHolder1$txtcardno': order.contact_info.get('id_number'),
            'ctl00$ContentPlaceHolder1$Imgbtnsubmit.x': '48',
            'ctl00$ContentPlaceHolder1$Imgbtnsubmit.y': '7',
        }
        r = requests.post(url, headers=headers,
                          cookies=r.cookies, data=urllib.urlencode(data))
        soup = bs(r.content, 'lxml')
        cardno = soup.find('input', attrs={'name': 'cardno'}).get(
            'value').strip()
        selectedseat = soup.find(
            'input', attrs={'name': 'selectedseat'}).get('value').strip()
        # print cardno, selectedseat
        # rebot_log.info(cardno + selectedseat)
        url = 'http://order.xuyunjt.com/wsdgnetcheck.aspx'
        data = {
            'buscode': line.extra_info.get('buscode'),
            'drivedate': line.extra_info.get('drivedate'),
            'plantime': line.extra_info.get('ccz').encode('utf-8') + ' ' + line.extra_info.get('time').encode('utf-8'),
            'selectedseat': selectedseat,
            'dstname': line.extra_info.get('dstname').encode('utf-8'),
            'incountry': line.extra_info.get('incountry'),
            'qp': pk,
            'jp': '0',
            'tp': '0',
            'total': pk,
            'cardno': cardno,
            'totalprice': line.full_price * pk,
        }
        data = urllib.urlencode(data)
        r = requests.post(url, headers=headers, cookies=r.cookies, data=data)
        soup = bs(r.content, 'lxml')
        state = soup.find(
            'input', attrs={'name': '__VIEWSTATE', 'id': '__VIEWSTATE'}).get('value', '')
        validation = soup.find('input', attrs={
            'name': '__EVENTVALIDATION', 'id': '__EVENTVALIDATION'}).get('value', '')
        data = {
            '__VIEWSTATE': state,
            '__EVENTVALIDATION': validation,
            'ctl00$ContentPlaceHolder1$hdfincountry': line.extra_info.get('incountry'),
            'ctl00$ContentPlaceHolder1$hdfselectedseat': selectedseat,
            'ctl00$ContentPlaceHolder1$alipaygroup': 'RBtnAlipay',
            'ctl00$ContentPlaceHolder1$Imgbtnsubmit.x': '55',
            'ctl00$ContentPlaceHolder1$Imgbtnsubmit.y': '19',
            'ctl00$ContentPlaceHolder1$TxtSubject': '徐运集团--长途汽车票',
            'ctl00$ContentPlaceHolder1$TxtBody': '',
        }
        cks = r.cookies
        # rebot_log.info(cks)
        r = requests.post(url, headers=headers, cookies=cks,
                          data=urllib.urlencode(data))
        soup = bs(r.content, 'lxml')
        no = soup.find(
            'span', attrs={'id': 'ctl00_ContentPlaceHolder1_lblout_trade_no'}).get_text()
        # ticketmessage = soup.find(
        #     'input', attrs={'name': 'ticketmessage'}).get('value').strip()
        # strconfirm = soup.find(
        #     'input', attrs={'name': 'strconfirm'}).get('value').strip()
        # rebot_log.info(no)
        # rebot_log.info(ticketmessage)
        # rebot_log.info(strconfirm)
        # print soup.form
        # lurl = 'http://order.xuyunjt.com/lastsubmit.aspx'
        # data = {}
        # data = {
        #     'sel': '0',
        #     'bespoke_id': no,
        #     'cardno': cardno,
        #     'number': '1',
        #     'money': line.full_price * pk,
        #     'ticketmessage': ticketmessage.encode('utf-8'),
        #     'strconfirm': strconfirm.encode('utf-8'),
        # }
        # headers['Referer'] = 'http://order.xuyunjt.com/wsdgnetcheck.aspx'
        # headers['Accept'] = 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8'
        # r = requests.post(lurl, headers=headers, cookies=cks,
        #                   data=urllib.urlencode(data))
        # soup = bs(r.content, 'lxml')
        # # rebot_log.info(soup)
        # state = soup.find(
        #     'input', attrs={'name': '__VIEWSTATE', 'id': '__VIEWSTATE'}).get('value', '')
        # validation = soup.find('input', attrs={
        #     'name': '__EVENTVALIDATION', 'id': '__EVENTVALIDATION'}).get('value', '')
        # data = {}
        # data = {
        #     '__VIEWSTATE': state,
        #     '__EVENTVALIDATION': validation,
        #     'ctl00$ContentPlaceHolder1$Imgbtnsubmit2.x': '124',
        #     'ctl00$ContentPlaceHolder1$Imgbtnsubmit2.y': '19',
        #     'ctl00$ContentPlaceHolder1$HDFcardno': cardno,
        #     'ctl00$ContentPlaceHolder1$HDFbespoke_id': no,
        #     'ctl00$ContentPlaceHolder1$hdfalipay_url': '',
        # }
        # r = requests.post(lurl, headers=headers, cookies=cks,
        #                   data=urllib.urlencode(data))
        # soup = bs(r.content, 'lxml')
        lurl = 'http://order.xuyunjt.com/lastsubmit.aspx'
        dcap = dict(DesiredCapabilities.PHANTOMJS)
        dcap["phantomjs.page.settings.userAgent"] = (
            "Mozilla/5.0 (Macintosh; Intel Mac OS X 10.9; rv:25.0) Gecko/20100101 Firefox/25.0 "
        )
        dr = webdriver.PhantomJS(desired_capabilities=dcap)
        tmp = {u'domain': u'xuyunjt.com',
               u'name': '',
               u'httpOnly': False,
               u'path': u'/',
               u'secure': False,
               u'value': ''}
        for k, v in cks.items():
            tmp['name'] = k
            tmp['value'] = v
        try:
            dr.add_cookie(tmp)
        except:
            pass
        dr.get(lurl)
        try:
            dr.find_element_by_id(
                "ctl00_ContentPlaceHolder1_Imgbtnsubmit2").click()
        except:
            pass
        soup = bs(dr.page_source, 'lxml')
        pay_url = soup.find_all('script')[-1].get_text()
        pay_url = pay_url.split("'")[1].strip()
        # dr.get(pay_url)
        # rebot_log.info(pay_url)
        # r = requests.get(lurl, headers=headers, cookies=cks)
        # soup = bs(r.content, 'lxml')
        if '在线支付确认' in soup.title.get_text() and pay_url:
            expire_time = dte.now() + datetime.timedelta(seconds=15 * 60)
            cookies = {}
            for x, y in cks.items():
                cookies[x] = y
            order.modify(extra_info={'cookies': json.dumps(
                cookies), 'pay_url': pay_url})
            lock_result.update({
                'result_code': 1,
                'raw_order_no': no,
                "expire_datetime": expire_time,
                "source_account": rebot.telephone,
                'pay_money': 0,
            })
            return lock_result
        else:
            lock_result.update({
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
        # elif '待付款' in state:
        #     result_info.update({
        #         "result_code": 2,
        #         "result_msg": state,
        #     })
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
            # rebot_log.info(result_info)
        return result_info

    # 线路刷新, java接口调用
    def do_refresh_line(self, line):
        url = 'http://order.xuyunjt.com/wsdgbccx.aspx'
        ste = line.extra_info.get('drivedate').replace('-', '')
        start_code = line.extra_info.get('incountry')
        end = line.extra_info.get('dstname')
        states = {
            '01320300001': '/wEPDwUKLTUzNTg5Njk5OA9kFgJmD2QWAgIDD2QWAgIHD2QWBgIFDxBkZBYBZmQCCQ8QDxYGHg1EYXRhVGV4dEZpZWxkBQlzYWxlX2RhdGUeDkRhdGFWYWx1ZUZpZWxkBQlzYWxlX2RhdGUeC18hRGF0YUJvdW5kZ2QQFQ8IMjAxNjA3MjEIMjAxNjA3MjIIMjAxNjA3MjMIMjAxNjA3MjQIMjAxNjA3MjUIMjAxNjA3MjYIMjAxNjA3MjcIMjAxNjA3MjgIMjAxNjA3MjkIMjAxNjA3MzAIMjAxNjA3MzEIMjAxNjA4MDEIMjAxNjA4MDIIMjAxNjA4MDMIMjAxNjA4MDQVDwgyMDE2MDcyMQgyMDE2MDcyMggyMDE2MDcyMwgyMDE2MDcyNAgyMDE2MDcyNQgyMDE2MDcyNggyMDE2MDcyNwgyMDE2MDcyOAgyMDE2MDcyOQgyMDE2MDczMAgyMDE2MDczMQgyMDE2MDgwMQgyMDE2MDgwMggyMDE2MDgwMwgyMDE2MDgwNBQrAw9nZ2dnZ2dnZ2dnZ2dnZ2dkZAIVD2QWAmYPZBYCAgEPPCsADQBkGAEFIGN0bDAwJENvbnRlbnRQbGFjZUhvbGRlcjEkR1ZCY2N4D2dkxrp0RdcFEUlBh0PfW5PN9xu8JOc=',
            '01320300002': '/wEPDwUKLTUzNTg5Njk5OA9kFgJmD2QWAgIDD2QWAgIHD2QWBgIFDxBkZBYBAgFkAgkPEA8WBh4NRGF0YVRleHRGaWVsZAUJc2FsZV9kYXRlHg5EYXRhVmFsdWVGaWVsZAUJc2FsZV9kYXRlHgtfIURhdGFCb3VuZGdkEBUPCDIwMTYwNzIxCDIwMTYwNzIyCDIwMTYwNzIzCDIwMTYwNzI0CDIwMTYwNzI1CDIwMTYwNzI2CDIwMTYwNzI3CDIwMTYwNzI4CDIwMTYwNzI5CDIwMTYwNzMwCDIwMTYwNzMxCDIwMTYwODAxCDIwMTYwODAyCDIwMTYwODAzCDIwMTYwODA0FQ8IMjAxNjA3MjEIMjAxNjA3MjIIMjAxNjA3MjMIMjAxNjA3MjQIMjAxNjA3MjUIMjAxNjA3MjYIMjAxNjA3MjcIMjAxNjA3MjgIMjAxNjA3MjkIMjAxNjA3MzAIMjAxNjA3MzEIMjAxNjA4MDEIMjAxNjA4MDIIMjAxNjA4MDMIMjAxNjA4MDQUKwMPZ2dnZ2dnZ2dnZ2dnZ2dnZGQCFQ9kFgJmD2QWAgIBDzwrAA0AZBgBBSBjdGwwMCRDb250ZW50UGxhY2VIb2xkZXIxJEdWQmNjeA9nZJa9OCrVIzH74yyPW2kJJFsp0i6G',
            '01320300003': '/wEPDwUKLTUzNTg5Njk5OA9kFgJmD2QWAgIDD2QWAgIHD2QWBgIFDxBkZBYBAgJkAgkPEA8WBh4NRGF0YVRleHRGaWVsZAUJc2FsZV9kYXRlHg5EYXRhVmFsdWVGaWVsZAUJc2FsZV9kYXRlHgtfIURhdGFCb3VuZGdkEBUPCDIwMTYwNzIxCDIwMTYwNzIyCDIwMTYwNzIzCDIwMTYwNzI0CDIwMTYwNzI1CDIwMTYwNzI2CDIwMTYwNzI3CDIwMTYwNzI4CDIwMTYwNzI5CDIwMTYwNzMwCDIwMTYwNzMxCDIwMTYwODAxCDIwMTYwODAyCDIwMTYwODAzCDIwMTYwODA0FQ8IMjAxNjA3MjEIMjAxNjA3MjIIMjAxNjA3MjMIMjAxNjA3MjQIMjAxNjA3MjUIMjAxNjA3MjYIMjAxNjA3MjcIMjAxNjA3MjgIMjAxNjA3MjkIMjAxNjA3MzAIMjAxNjA3MzEIMjAxNjA4MDEIMjAxNjA4MDIIMjAxNjA4MDMIMjAxNjA4MDQUKwMPZ2dnZ2dnZ2dnZ2dnZ2dnZGQCFQ9kFgJmD2QWAgIBDzwrAA0AZBgBBSBjdGwwMCRDb250ZW50UGxhY2VIb2xkZXIxJEdWQmNjeA9nZFNqeRc73oNo2GLyRYFnifWRKPJe',
            '01320300006': '/wEPDwUKLTUzNTg5Njk5OA9kFgJmD2QWAgIDD2QWAgIHD2QWBgIFDxBkZBYBAgNkAgkPEA8WBh4NRGF0YVRleHRGaWVsZAUJc2FsZV9kYXRlHg5EYXRhVmFsdWVGaWVsZAUJc2FsZV9kYXRlHgtfIURhdGFCb3VuZGdkEBUPCDIwMTYwNzIxCDIwMTYwNzIyCDIwMTYwNzIzCDIwMTYwNzI0CDIwMTYwNzI1CDIwMTYwNzI2CDIwMTYwNzI3CDIwMTYwNzI4CDIwMTYwNzI5CDIwMTYwNzMwCDIwMTYwNzMxCDIwMTYwODAxCDIwMTYwODAyCDIwMTYwODAzCDIwMTYwODA0FQ8IMjAxNjA3MjEIMjAxNjA3MjIIMjAxNjA3MjMIMjAxNjA3MjQIMjAxNjA3MjUIMjAxNjA3MjYIMjAxNjA3MjcIMjAxNjA3MjgIMjAxNjA3MjkIMjAxNjA3MzAIMjAxNjA3MzEIMjAxNjA4MDEIMjAxNjA4MDIIMjAxNjA4MDMIMjAxNjA4MDQUKwMPZ2dnZ2dnZ2dnZ2dnZ2dnZGQCFQ9kFgJmD2QWAgIBDzwrAA0AZBgBBSBjdGwwMCRDb250ZW50UGxhY2VIb2xkZXIxJEdWQmNjeA9nZKDSPSiXBJis2bC5A2bj+L8/FTrw',
            '01320322001': '/wEPDwUKLTUzNTg5Njk5OA9kFgJmD2QWAgIDD2QWAgIHD2QWBgIFDxBkZBYBAgRkAgkPEA8WBh4NRGF0YVRleHRGaWVsZAUJc2FsZV9kYXRlHg5EYXRhVmFsdWVGaWVsZAUJc2FsZV9kYXRlHgtfIURhdGFCb3VuZGdkEBUPCDIwMTYwNzIxCDIwMTYwNzIyCDIwMTYwNzIzCDIwMTYwNzI0CDIwMTYwNzI1CDIwMTYwNzI2CDIwMTYwNzI3CDIwMTYwNzI4CDIwMTYwNzI5CDIwMTYwNzMwCDIwMTYwNzMxCDIwMTYwODAxCDIwMTYwODAyCDIwMTYwODAzCDIwMTYwODA0FQ8IMjAxNjA3MjEIMjAxNjA3MjIIMjAxNjA3MjMIMjAxNjA3MjQIMjAxNjA3MjUIMjAxNjA3MjYIMjAxNjA3MjcIMjAxNjA3MjgIMjAxNjA3MjkIMjAxNjA3MzAIMjAxNjA3MzEIMjAxNjA4MDEIMjAxNjA4MDIIMjAxNjA4MDMIMjAxNjA4MDQUKwMPZ2dnZ2dnZ2dnZ2dnZ2dnZGQCFQ9kFgJmD2QWAgIBDzwrAA0AZBgBBSBjdGwwMCRDb250ZW50UGxhY2VIb2xkZXIxJEdWQmNjeA9nZDNUxBq0L6Jh0zqmYSO3e8ZsZ7Lt',
            '01320322002': '/wEPDwUKLTUzNTg5Njk5OA9kFgJmD2QWAgIDD2QWAgIHD2QWBgIFDxBkZBYBAgVkAgkPEA8WBh4NRGF0YVRleHRGaWVsZAUJc2FsZV9kYXRlHg5EYXRhVmFsdWVGaWVsZAUJc2FsZV9kYXRlHgtfIURhdGFCb3VuZGdkEBUPCDIwMTYwNzIxCDIwMTYwNzIyCDIwMTYwNzIzCDIwMTYwNzI0CDIwMTYwNzI1CDIwMTYwNzI2CDIwMTYwNzI3CDIwMTYwNzI4CDIwMTYwNzI5CDIwMTYwNzMwCDIwMTYwNzMxCDIwMTYwODAxCDIwMTYwODAyCDIwMTYwODAzCDIwMTYwODA0FQ8IMjAxNjA3MjEIMjAxNjA3MjIIMjAxNjA3MjMIMjAxNjA3MjQIMjAxNjA3MjUIMjAxNjA3MjYIMjAxNjA3MjcIMjAxNjA3MjgIMjAxNjA3MjkIMjAxNjA3MzAIMjAxNjA3MzEIMjAxNjA4MDEIMjAxNjA4MDIIMjAxNjA4MDMIMjAxNjA4MDQUKwMPZ2dnZ2dnZ2dnZ2dnZ2dnZGQCFQ9kFgJmD2QWAgIBDzwrAA0AZBgBBSBjdGwwMCRDb250ZW50UGxhY2VIb2xkZXIxJEdWQmNjeA9nZB8gvGdl+trbSks8ldMN3LWu7uUm',
            '01320321001': '/wEPDwUKLTUzNTg5Njk5OA9kFgJmD2QWAgIDD2QWAgIHD2QWBgIFDxBkZBYBAgZkAgkPEA8WBh4NRGF0YVRleHRGaWVsZAUJc2FsZV9kYXRlHg5EYXRhVmFsdWVGaWVsZAUJc2FsZV9kYXRlHgtfIURhdGFCb3VuZGdkEBUPCDIwMTYwNzIxCDIwMTYwNzIyCDIwMTYwNzIzCDIwMTYwNzI0CDIwMTYwNzI1CDIwMTYwNzI2CDIwMTYwNzI3CDIwMTYwNzI4CDIwMTYwNzI5CDIwMTYwNzMwCDIwMTYwNzMxCDIwMTYwODAxCDIwMTYwODAyCDIwMTYwODAzCDIwMTYwODA0FQ8IMjAxNjA3MjEIMjAxNjA3MjIIMjAxNjA3MjMIMjAxNjA3MjQIMjAxNjA3MjUIMjAxNjA3MjYIMjAxNjA3MjcIMjAxNjA3MjgIMjAxNjA3MjkIMjAxNjA3MzAIMjAxNjA3MzEIMjAxNjA4MDEIMjAxNjA4MDIIMjAxNjA4MDMIMjAxNjA4MDQUKwMPZ2dnZ2dnZ2dnZ2dnZ2dnZGQCFQ9kFgJmD2QWAgIBDzwrAA0AZBgBBSBjdGwwMCRDb250ZW50UGxhY2VIb2xkZXIxJEdWQmNjeA9nZFZXtBaKPhmConurif7szMlsVdku',
            '01320382001': '/wEPDwUKLTUzNTg5Njk5OA9kFgJmD2QWAgIDD2QWAgIHD2QWBgIFDxBkZBYBAgdkAgkPEA8WBh4NRGF0YVRleHRGaWVsZAUJc2FsZV9kYXRlHg5EYXRhVmFsdWVGaWVsZAUJc2FsZV9kYXRlHgtfIURhdGFCb3VuZGdkEBUPCDIwMTYwNzIxCDIwMTYwNzIyCDIwMTYwNzIzCDIwMTYwNzI0CDIwMTYwNzI1CDIwMTYwNzI2CDIwMTYwNzI3CDIwMTYwNzI4CDIwMTYwNzI5CDIwMTYwNzMwCDIwMTYwNzMxCDIwMTYwODAxCDIwMTYwODAyCDIwMTYwODAzCDIwMTYwODA0FQ8IMjAxNjA3MjEIMjAxNjA3MjIIMjAxNjA3MjMIMjAxNjA3MjQIMjAxNjA3MjUIMjAxNjA3MjYIMjAxNjA3MjcIMjAxNjA3MjgIMjAxNjA3MjkIMjAxNjA3MzAIMjAxNjA3MzEIMjAxNjA4MDEIMjAxNjA4MDIIMjAxNjA4MDMIMjAxNjA4MDQUKwMPZ2dnZ2dnZ2dnZ2dnZ2dnZGQCFQ9kFgJmD2QWAgIBDzwrAA0AZBgBBSBjdGwwMCRDb250ZW50UGxhY2VIb2xkZXIxJEdWQmNjeA9nZCS9vMoyTIUl4YblyXSB7g9oaZYq',
            '01320382002': '/wEPDwUKLTUzNTg5Njk5OA9kFgJmD2QWAgIDD2QWAgIHD2QWBgIFDxBkZBYBAghkAgkPEA8WBh4NRGF0YVRleHRGaWVsZAUJc2FsZV9kYXRlHg5EYXRhVmFsdWVGaWVsZAUJc2FsZV9kYXRlHgtfIURhdGFCb3VuZGdkEBUPCDIwMTYwNzIxCDIwMTYwNzIyCDIwMTYwNzIzCDIwMTYwNzI0CDIwMTYwNzI1CDIwMTYwNzI2CDIwMTYwNzI3CDIwMTYwNzI4CDIwMTYwNzI5CDIwMTYwNzMwCDIwMTYwNzMxCDIwMTYwODAxCDIwMTYwODAyCDIwMTYwODAzCDIwMTYwODA0FQ8IMjAxNjA3MjEIMjAxNjA3MjIIMjAxNjA3MjMIMjAxNjA3MjQIMjAxNjA3MjUIMjAxNjA3MjYIMjAxNjA3MjcIMjAxNjA3MjgIMjAxNjA3MjkIMjAxNjA3MzAIMjAxNjA3MzEIMjAxNjA4MDEIMjAxNjA4MDIIMjAxNjA4MDMIMjAxNjA4MDQUKwMPZ2dnZ2dnZ2dnZ2dnZ2dnZGQCFQ9kFgJmD2QWAgIBDzwrAA0AZBgBBSBjdGwwMCRDb250ZW50UGxhY2VIb2xkZXIxJEdWQmNjeA9nZMueQPyBQvYm5rnIWjkVBWMB8NVp',
            '01320382003': '/wEPDwUKLTUzNTg5Njk5OA9kFgJmD2QWAgIDD2QWAgIHD2QWBgIFDxBkZBYBAglkAgkPEA8WBh4NRGF0YVRleHRGaWVsZAUJc2FsZV9kYXRlHg5EYXRhVmFsdWVGaWVsZAUJc2FsZV9kYXRlHgtfIURhdGFCb3VuZGdkEBUPCDIwMTYwNzIxCDIwMTYwNzIyCDIwMTYwNzIzCDIwMTYwNzI0CDIwMTYwNzI1CDIwMTYwNzI2CDIwMTYwNzI3CDIwMTYwNzI4CDIwMTYwNzI5CDIwMTYwNzMwCDIwMTYwNzMxCDIwMTYwODAxCDIwMTYwODAyCDIwMTYwODAzCDIwMTYwODA0FQ8IMjAxNjA3MjEIMjAxNjA3MjIIMjAxNjA3MjMIMjAxNjA3MjQIMjAxNjA3MjUIMjAxNjA3MjYIMjAxNjA3MjcIMjAxNjA3MjgIMjAxNjA3MjkIMjAxNjA3MzAIMjAxNjA3MzEIMjAxNjA4MDEIMjAxNjA4MDIIMjAxNjA4MDMIMjAxNjA4MDQUKwMPZ2dnZ2dnZ2dnZ2dnZ2dnZGQCFQ9kFgJmD2QWAgIBDzwrAA0AZBgBBSBjdGwwMCRDb250ZW50UGxhY2VIb2xkZXIxJEdWQmNjeA9nZPILlCOrprDPOHtjKAPiEU0hXFeG',
            '01320381001': '/wEPDwUKLTUzNTg5Njk5OA9kFgJmD2QWAgIDD2QWAgIHD2QWBgIFDxBkZBYBAgpkAgkPEA8WBh4NRGF0YVRleHRGaWVsZAUJc2FsZV9kYXRlHg5EYXRhVmFsdWVGaWVsZAUJc2FsZV9kYXRlHgtfIURhdGFCb3VuZGdkEBUPCDIwMTYwNzIxCDIwMTYwNzIyCDIwMTYwNzIzCDIwMTYwNzI0CDIwMTYwNzI1CDIwMTYwNzI2CDIwMTYwNzI3CDIwMTYwNzI4CDIwMTYwNzI5CDIwMTYwNzMwCDIwMTYwNzMxCDIwMTYwODAxCDIwMTYwODAyCDIwMTYwODAzCDIwMTYwODA0FQ8IMjAxNjA3MjEIMjAxNjA3MjIIMjAxNjA3MjMIMjAxNjA3MjQIMjAxNjA3MjUIMjAxNjA3MjYIMjAxNjA3MjcIMjAxNjA3MjgIMjAxNjA3MjkIMjAxNjA3MzAIMjAxNjA3MzEIMjAxNjA4MDEIMjAxNjA4MDIIMjAxNjA4MDMIMjAxNjA4MDQUKwMPZ2dnZ2dnZ2dnZ2dnZ2dnZGQCFQ9kFgJmD2QWAgIBDzwrAA0AZBgBBSBjdGwwMCRDb250ZW50UGxhY2VIb2xkZXIxJEdWQmNjeA9nZFZWkDjvo0ZkY4IkgS/zOH/psub7',
            '01320381002': '/wEPDwUKLTUzNTg5Njk5OA9kFgJmD2QWAgIDD2QWAgIHD2QWBgIFDxBkZBYBAgtkAgkPEA8WBh4NRGF0YVRleHRGaWVsZAUJc2FsZV9kYXRlHg5EYXRhVmFsdWVGaWVsZAUJc2FsZV9kYXRlHgtfIURhdGFCb3VuZGdkEBUPCDIwMTYwNzIxCDIwMTYwNzIyCDIwMTYwNzIzCDIwMTYwNzI0CDIwMTYwNzI1CDIwMTYwNzI2CDIwMTYwNzI3CDIwMTYwNzI4CDIwMTYwNzI5CDIwMTYwNzMwCDIwMTYwNzMxCDIwMTYwODAxCDIwMTYwODAyCDIwMTYwODAzCDIwMTYwODA0FQ8IMjAxNjA3MjEIMjAxNjA3MjIIMjAxNjA3MjMIMjAxNjA3MjQIMjAxNjA3MjUIMjAxNjA3MjYIMjAxNjA3MjcIMjAxNjA3MjgIMjAxNjA3MjkIMjAxNjA3MzAIMjAxNjA3MzEIMjAxNjA4MDEIMjAxNjA4MDIIMjAxNjA4MDMIMjAxNjA4MDQUKwMPZ2dnZ2dnZ2dnZ2dnZ2dnZGQCFQ9kFgJmD2QWAgIBDzwrAA0AZBgBBSBjdGwwMCRDb250ZW50UGxhY2VIb2xkZXIxJEdWQmNjeA9nZNDBH5g2EYIuia2D6W9T7+MlANrY',
            '01320324001': '/wEPDwUKLTUzNTg5Njk5OA9kFgJmD2QWAgIDD2QWAgIHD2QWBgIFDxBkZBYBAgxkAgkPEA8WBh4NRGF0YVRleHRGaWVsZAUJc2FsZV9kYXRlHg5EYXRhVmFsdWVGaWVsZAUJc2FsZV9kYXRlHgtfIURhdGFCb3VuZGdkEBUPCDIwMTYwNzIxCDIwMTYwNzIyCDIwMTYwNzIzCDIwMTYwNzI0CDIwMTYwNzI1CDIwMTYwNzI2CDIwMTYwNzI3CDIwMTYwNzI4CDIwMTYwNzI5CDIwMTYwNzMwCDIwMTYwNzMxCDIwMTYwODAxCDIwMTYwODAyCDIwMTYwODAzCDIwMTYwODA0FQ8IMjAxNjA3MjEIMjAxNjA3MjIIMjAxNjA3MjMIMjAxNjA3MjQIMjAxNjA3MjUIMjAxNjA3MjYIMjAxNjA3MjcIMjAxNjA3MjgIMjAxNjA3MjkIMjAxNjA3MzAIMjAxNjA3MzEIMjAxNjA4MDEIMjAxNjA4MDIIMjAxNjA4MDMIMjAxNjA4MDQUKwMPZ2dnZ2dnZ2dnZ2dnZ2dnZGQCFQ9kFgJmD2QWAgIBDzwrAA0AZBgBBSBjdGwwMCRDb250ZW50UGxhY2VIb2xkZXIxJEdWQmNjeA9nZEIAoUCYdEMWBoh/UPeXhFtAQ31c',
            '01320300702': '/wEPDwUKLTUzNTg5Njk5OA9kFgJmD2QWAgIDD2QWAgIHD2QWBgIFDxBkZBYBAg1kAgkPEA8WBh4NRGF0YVRleHRGaWVsZAUJc2FsZV9kYXRlHg5EYXRhVmFsdWVGaWVsZAUJc2FsZV9kYXRlHgtfIURhdGFCb3VuZGdkEBUPCDIwMTYwNzIxCDIwMTYwNzIyCDIwMTYwNzIzCDIwMTYwNzI0CDIwMTYwNzI1CDIwMTYwNzI2CDIwMTYwNzI3CDIwMTYwNzI4CDIwMTYwNzI5CDIwMTYwNzMwCDIwMTYwNzMxCDIwMTYwODAxCDIwMTYwODAyCDIwMTYwODAzCDIwMTYwODA0FQ8IMjAxNjA3MjEIMjAxNjA3MjIIMjAxNjA3MjMIMjAxNjA3MjQIMjAxNjA3MjUIMjAxNjA3MjYIMjAxNjA3MjcIMjAxNjA3MjgIMjAxNjA3MjkIMjAxNjA3MzAIMjAxNjA3MzEIMjAxNjA4MDEIMjAxNjA4MDIIMjAxNjA4MDMIMjAxNjA4MDQUKwMPZ2dnZ2dnZ2dnZ2dnZ2dnZGQCFQ9kFgJmD2QWAgIBDzwrAA0AZBgBBSBjdGwwMCRDb250ZW50UGxhY2VIb2xkZXIxJEdWQmNjeA9nZKVeON+dNEJJq67eBloN9FWWHeFZ',
            '01320300703': '/wEPDwUKLTUzNTg5Njk5OA9kFgJmD2QWAgIDD2QWAgIHD2QWBgIFDxBkZBYBAg5kAgkPEA8WBh4NRGF0YVRleHRGaWVsZAUJc2FsZV9kYXRlHg5EYXRhVmFsdWVGaWVsZAUJc2FsZV9kYXRlHgtfIURhdGFCb3VuZGdkEBUPCDIwMTYwNzIxCDIwMTYwNzIyCDIwMTYwNzIzCDIwMTYwNzI0CDIwMTYwNzI1CDIwMTYwNzI2CDIwMTYwNzI3CDIwMTYwNzI4CDIwMTYwNzI5CDIwMTYwNzMwCDIwMTYwNzMxCDIwMTYwODAxCDIwMTYwODAyCDIwMTYwODAzCDIwMTYwODA0FQ8IMjAxNjA3MjEIMjAxNjA3MjIIMjAxNjA3MjMIMjAxNjA3MjQIMjAxNjA3MjUIMjAxNjA3MjYIMjAxNjA3MjcIMjAxNjA3MjgIMjAxNjA3MjkIMjAxNjA3MzAIMjAxNjA3MzEIMjAxNjA4MDEIMjAxNjA4MDIIMjAxNjA4MDMIMjAxNjA4MDQUKwMPZ2dnZ2dnZ2dnZ2dnZ2dnZGQCFQ9kFgJmD2QWAgIBDzwrAA0AZBgBBSBjdGwwMCRDb250ZW50UGxhY2VIb2xkZXIxJEdWQmNjeA9nZKETdkimIZ6HF/kPjX3Yt4Ft0itJ',
        }
        data = {
            'ctl00$ContentPlaceHolder1$ScriptManager1': 'ctl00$ContentPlaceHolder1$ScriptManager1|ctl00$ContentPlaceHolder1$BtnBccx',
            'ctl00$ContentPlaceHolder1$BtnBccx': '班次查询',
            '__EVENTARGUMENT': '',
            '__LASTFOCUS': '',
            '__VIEWSTATE': states[start_code],
            'ctl00$ContentPlaceHolder1$ddlincounty': start_code,
            'ctl00$ContentPlaceHolder1$ddlsaledate': ste,
            'ctl00$ContentPlaceHolder1$txtstop': end,
            'radio': end,
        }
        ua = random.choice(BROWSER_USER_AGENT)
        headers = {"User-Agent": ua,
                   "Content-Type": "application/x-www-form-urlencoded",
                   'X-MicrosoftAjax': 'Delta=true',
                   }
        r = requests.post(url, headers=headers, data=urllib.urlencode(data))
        soup = bs(r.content, 'lxml')
        info = soup.find('table', attrs={'id': 'ctl00_ContentPlaceHolder1_GVBccx'}).find_all(
            'tr', attrs={'class': True})
        now = dte.now()
        update_attrs = {}
        ft = Line.objects.filter(s_city_name=line.s_city_name,
                                 d_city_name=line.d_city_name, drv_date=line.drv_date)
        t = {x.line_id: x for x in ft}
        update_attrs = {}
        for x in info[1:]:
            try:
                y = x.find_all('td')
                drv_date = y[0].get_text().strip()
                s_sta_name = y[1].get_text().strip()
                d_city_name = y[3].get_text().strip()
                drv_time = y[5].get_text().strip()
                left_tickets = int(y[8].get_text().strip())
                drv_datetime = dte.strptime("%s %s" % (
                    drv_date, drv_time), "%Y-%m-%d %H:%M")
                line_id_args = {
                    "s_city_name": line.s_city_name,
                    "d_city_name": line.d_city_name,
                    "s_sta_name": s_sta_name,
                    "d_sta_name": d_city_name,
                    "crawl_source": line.crawl_source,
                    "drv_datetime": drv_datetime,
                }
                line_id = md5("%(s_city_name)s-%(d_city_name)s-%(drv_datetime)s-%(s_sta_name)s-%(d_sta_name)s-%(crawl_source)s" % line_id_args)
                if line_id in t:
                    t[line_id].update(
                        **{"left_tickets": left_tickets, "refresh_datetime": now})
                if line_id == line.line_id:
                    update_attrs = {
                        "left_tickets": left_tickets, "refresh_datetime": now}
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

        # 获取alipay付款界面
        def _get_page(rebot):
            if order.status == STATUS_WAITING_ISSUE:
                pay_url = order.extra_info.get('pay_url')
                # cks = json.loads(order.extra_info.get('cookies'))
                # headers = {
                #     "User-Agent": rebot.user_agent,
                #     # "Content-Type": "application/x-www-form-urlencoded",
                # }
                # dr = webdriver.PhantomJS()
                # tmp = {u'domain': u'xuyunjt.com',
                #        u'name': '',
                #        u'httpOnly': False,
                #        u'path': u'/',
                #        u'secure': False,
                #        u'value': ''}
                # for k in cks.keys():
                #     tmp['name'] = k
                #     tmp['value'] = cks.get(k, '')
                # try:
                #     dr.add_cookie(tmp)
                # except:
                #     pass
                # dr.get(pay_url)
                # try:
                #     dr.find_element_by_id(
                #         "ctl00_ContentPlaceHolder1_Imgbtnsubmit2").click()
                # except:
                #     pass
                # soup = bs(dr.page_source, 'lxml')
                # pay_url = soup.find_all('script')[-1].get_text()
                # pay_url = pay_url.split("'")[1].strip()
                # # dr.get(pay_url)
                # rebot_log.info(pay_url)
                # headers['Accept-Language'] = 'zh-CN,zh;q=0.8,en-US;q=0.5,en;q=0.3'
                # headers['Accept-Encoding'] = 'gzip, deflate, br'
                # headers['Host'] = 'kcart.alipay.com'
                # r = requests.get(pay_url, headers=headers, cookies=cks)
                # soup = bs(r.content, 'lxml')
                # info = soup.find(
                #     'li', attrs={'class': 'order-item'}).find_all('tr')
                # trade_no = info[1].get_text()
                # trade_no = re.findall(r'\d+', trade_no)[0]
                # pay_money = info[-1].get_text()
                # pay_money = float(re.findall(r'\d+\.\d+', pay_money)[0])
                # # rebot_log.info(pay_money)
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
        if order.status in [STATUS_LOCK_RETRY, STATUS_WAITING_LOCK]:
            self.lock_ticket(order)

        if order.status == STATUS_WAITING_ISSUE:
            return _get_page(rebot)
