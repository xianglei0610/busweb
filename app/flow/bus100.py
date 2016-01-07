# -*- coding:utf-8 -*-
import random
import urllib2
import requests
import datetime
import json
import re
from datetime import datetime as dte
from flask import render_template, request, redirect
from lxml import etree

from app.constants import *
from app.flow.base import Flow as BaseFlow
from app.models import Bus100Rebot, Line
from app.flow import get_flow


class Flow(BaseFlow):
    name = "bus100"

    def do_lock_ticket(self, order):
        lock_result = {
            "lock_info": {},
            "source_account": '',
            "result_code": 0,
            "result_reason": "",
            "pay_url": "",
            "raw_order_no": "",
            "expire_datetime": "",
            "pay_money": 0,
        }
        rebot = Bus100Rebot.get_random_rebot()
        if not rebot:
            rebot = Bus100Rebot.objects.first()
            lock_result.update(result_code=2)
            lock_result.update(source_account=rebot.telephone)
            return lock_result
        rebot.recrawl_shiftid(order.line)
        line = Line.objects.get(line_id=order.line.line_id)
        order.line = line
        order.ticket_price = line.full_price
        order.save()

        lock_result.update(source_account=rebot.telephone)

        if order.line.bus_num == 0 or not order.line.extra_info.get('flag', 0):
            lock_result.update(result_reason="该条线路无法购买")
            return lock_result
        ticketType = u'全票'
        ticketPassword = ''

        url = 'http://www.84100.com/getTrainInfo/ajax'
        data = {
              "shiftId": order.line.bus_num,
              "startId": order.line.starting.station_id,
              "startName": order.line.starting.station_name,
              "ttsId":  ''
        }
        trainInfo = requests.post(url, data=data, cookies=rebot.cookies)
        trainInfo = trainInfo.json()
        tickType = trainInfo['tickType']
        if re.findall(u'全票', tickType) or re.findall('\u5168\u7968', tickType):
            ticketType = u'全票'
        else:
            if re.findall(u'全', tickType):
                ticketType = u'全'

        msg = trainInfo['msg']
        if re.findall('ticketPassword', msg):
            ticketPassword = str(random.randint(100000, 999999))
        else:
            ticketPassword = ''

        url = 'http://www.84100.com/createOrder/ajax'
        idNos = []
        names = []
        ticketTypes = []
        idTypes = []
        for r in order.riders:
            idNos.append(r["id_number"])
            names.append(r["name"])
            idTypes.append(str(r["id_type"]))
            ticketTypes.append(ticketType)

        data = {
            "startId": order.line.starting.station_id,
            "planId": order.line.bus_num,
            "name": order.contact_info['name'],
            "mobile": order.contact_info['telephone'],
            "ticketNo": '',
            "ticketPassword": ticketPassword,
            "idNos": ','.join(idNos),
            "ticketTypes": ','.join(ticketTypes),
            "idTypes": ','.join(idTypes),
            "names": ','.join(names),
        }
        print data
        orderInfo = requests.post(url, data=data, cookies=rebot.cookies)
        orderInfo = orderInfo.json()
        pay_url = ''
        if orderInfo.get('flag') == '0':
            orderId = orderInfo['orderId']
            url = "http://www.84100.com/pay/ajax?orderId=%s" % orderId
            orderPay = requests.post(url, cookies=rebot.cookies)
            orderPay = orderPay.json()
            if orderPay.get('flag') == '0':
                pay_url = orderPay['url']

        if pay_url:
            pay_info = self.request_pay_info(pay_url)
            expire_datetime = dte.now()+datetime.timedelta(seconds=20*60)
            orderInfo['expire_datetime'] = expire_datetime
            orderInfo['ticketPassword'] = ticketPassword
            lock_result.update({
                "result_code": 1,
                "lock_info": orderInfo,
                "pay_url": pay_url,
                "raw_order_no": orderId,
                "expire_datetime": expire_datetime,
                "pay_money": pay_info["pay_money"]
            })
        else:
            lock_result.update({
                "lock_info": orderInfo,
                "result_reason": orderInfo.get('msg', ''),
            })
        return lock_result

    def request_pay_info(self, pay_url):
        ua = random.choice(MOBILE_USER_AGENG)
        headers = {"User-Agent": ua}
        r = requests.get(pay_url, verify=False,  headers=headers)
        sel = etree.HTML(r.content)
        orderNoObj = sel.xpath('//form[@id="openUnionPayForm"]/input[@id="orderNo"]/@value')
        orderAmtObj = sel.xpath('//form[@id="openUnionPayForm"]/input[@id="orderAmt"]/@value')
        return {"order_no": orderNoObj[0], "pay_money": float(orderAmtObj[0])}

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

        rebot = Bus100Rebot.objects.get(telephone=order.source_account)
        tickets = self.send_order_request(order, rebot)
        code_list, msg_list = [], []
        status = tickets.get("status", None)
        if status == '4':
            dx_templ = DUAN_XIN_TEMPL[SOURCE_BUS100]
            dx_info = {
                "amount": order.ticket_amount,
                "start": "%s(%s)" % (order.line.starting.city_name, order.line.starting.station_name),
                "end": order.line.destination.station_name,
                "time": order.drv_datetime.strftime("%Y-%m-%d %H:%M"),
                "order": tickets["order_id"],
            }
            if order.lock_info.get('ticketPassword', ''):
                code_list.append(order.lock_info.get('ticketPassword', ''))
            else:
                code_list.append('无需取票密码')
            msg_list.append(dx_templ % dx_info)
            result_info.update({
                "result_code": 1,
                "result_msg": "",
                "pick_code_list": code_list,
                "pick_msg_list": msg_list,
            })
        elif status == '5':
            result_info.update(result_code=2, result_msg="")
        elif status == '6':
            result_info.update(result_code=4, result_msg="正在出票")
        return result_info

    def send_order_request(self, order, rebot):
        data = {"orderId": order.raw_order_no}
        url = "http://www.84100.com/orderInfo.shtml"
        r = requests.post(url, data=data, cookies=rebot.cookies)
        sel = etree.HTML(r.content)
        orderDetailObj = sel.xpath('//div[@class="order-details"]/ul')
        orderDetail = {}
        if orderDetailObj:
            status = orderDetailObj[0].xpath('li')[1].xpath('em/text()')[0].replace('\r\n','').replace(' ','')
            if status == u'正在出票' or status == u'\xe6\xad\xa3\xe5\x9c\xa8\xe5\x87\xba\xe7\xa5\xa8':
                orderDetail.update({'status': '6'})
            elif status == u"购票成功" or status == u'\xe8\xb4\xad\xe7\xa5\xa8\xe6\x88\x90\xe5\x8a\x9f':
                orderDetail.update({'status': '4'})
                matchObj = re.findall('<li>订单号：(.*)', r.content)
                order_id = matchObj[0].replace(' ','')
                orderDetail.update({'order_id': order_id})
            elif status == u"订单失效" or status == u'\xe8\xae\xa2\xe5\x8d\x95\xe5\xa4\xb1\xe6\x95\x88':
                orderDetail.update({'status': '5'})
        return orderDetail

    def mock_send_order_request(self, order, rebot):
        return {"status": "4", "order_id": "1111111111111"}

    def do_refresh_line(self, line):
        result_info = {
            "result_msg": "",
            "update_attrs": {},
        }
        rebot = Bus100Rebot.get_random_rebot()
        if not rebot:
            return result_info
        ret = rebot.recrawl_shiftid(line)
        line = Line.objects.get(line_id=line.line_id)
        url = 'http://www.84100.com/getTrainInfo/ajax'
        payload = {
            "shiftId": line.bus_num,
            "startId": line.starting.station_id,
            "startName": line.starting.station_name,
            "ttsId": ''
        }
        now = dte.now()
        try:
            trainInfo = requests.post(url, data=payload, cookies=rebot.cookies)
            trainInfo = trainInfo.json()
            left_tickets = 0
            if str(trainInfo['flag']) == '0':
                sel = etree.HTML(trainInfo['msg'])
                left_tickets = sel.xpath('//div[@class="ticketPrice"]/ul/li/strong[@id="leftSeatNum"]/text()')
                if left_tickets:
                    left_tickets = int(left_tickets[0])
            result_info.update(result_msg="ok", update_attrs={"left_tickets": left_tickets, "refresh_datetime": now})
        except:
            result_info.update(result_msg="fail", update_attrs={"left_tickets": 0, "refresh_datetime": now})
        return result_info

    def get_pay_page(self, order, valid_code="", session=None, **kwargs):

        headers = {
            'User-Agent': "Mozilla/5.0 (Windows NT 6.2) AppleWebKit/536.3  (KHTML, like Gecko) Chrome/19.0.1061.0 Safari/536.3",
        }
        pay_url = order.pay_url
        code = valid_code
        # 验证码处理
        flag = False
        ret = {}
        if code:
            data = json.loads(session["bus100_pay_login_info"])
            code_url = data["valid_url"]
            headers = data["headers"]
            cookies = data["cookies"]
            flag = True
        else:
            login_form_url = "http://84100.com/login.shtml"
            r = requests.get(login_form_url, headers=headers)
            sel = etree.HTML(r.content)
            cookies = dict(r.cookies)
            code_url = sel.xpath("//img[@id='validateImg']/@src")[0]
            code_url = 'http://84100.com'+code_url
            r = requests.get(code_url, headers=headers, cookies=cookies)
            cookies.update(dict(r.cookies))
        if flag:
            accounts = SOURCE_INFO[SOURCE_BUS100]["accounts"]
            passwd, _ = accounts[order.source_account]
            data = {
                "loginType": 0,
                "backUrl": '',
                "mobile": order.source_account,
                "password": passwd,
                "validateCode": code
            }
            r = requests.post("http://84100.com/doLogin/ajax", data=data, headers=headers, cookies=cookies)
            cookies.update(dict(r.cookies))
            ret = r.json()
            print ret,'333333333333333333333333333',code
        if ret.get("flag", '') == '0':
            rebot = Bus100Rebot.objects.get(telephone=order.source_account)
            rebot.cookies = cookies
            print cookies
            rebot.is_active = True
            rebot.save()
            flow = get_flow(order.crawl_source)
            flow.lock_ticket(order)
            pay_url = order.pay_url
        if pay_url:
            headers = {
                'User-Agent': "Mozilla/5.0 (Windows NT 6.1; WOW64; rv:42.0) Gecko/20100101 Firefox/42.0",
            }
            r = requests.get(pay_url, headers=headers, verify=False)
            cookies = dict(r.cookies)
            sel = etree.HTML(r.content)
            try:
                paySource = sel.xpath('//input[@id="paySource"]/@value')[0]
                if paySource == '84100YK':
                    payment = '10'
                else:
                    payment = '5'
                data = dict(
                        userIdentifier=sel.xpath('//form[@id="alipayForm"]/input[@name="userIdentifier"]/@value')[0],
                        orderNo=sel.xpath('//form[@id="alipayForm"]/input[@name="orderNo"]/@value')[0],
                        couponId=sel.xpath('//form[@id="alipayForm"]/input[@name="couponId"]/@value')[0],
                        produceType=sel.xpath('//form[@id="alipayForm"]/input[@name="produceType"]/@value')[0],
                        payment=payment
                    )
                print data
                info_url = "http://pay.84100.com/payment/payment/gateWayPay.do"
                r = requests.post(info_url, data=data, headers=headers, cookies=cookies, verify=False)
                return {"flag": "html", "content": r.content}
            except:
                return {"flag": "url", "content": pay_url}

        if ret.get("msg", '') == "验证码不正确" or not flag:
            data = {
                "cookies": cookies,
                "headers": headers,
                "valid_url": code_url,
            }
            session["bus100_pay_login_info"] = json.dumps(data)
            return {"flag": "input_code", "content": ""}

