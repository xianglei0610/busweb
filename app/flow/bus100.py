# -*- coding:utf-8 -*-
import random
import requests
import datetime
import json
import re
import urllib

from datetime import datetime as dte
from lxml import etree
from app.constants import *
from app.flow.base import Flow as BaseFlow
from app.models import Bus100Rebot, Line
from app import order_log, line_log


class Flow(BaseFlow):
    name = "bus100"

    def do_lock_ticket(self, order):
        lock_result = {
            "lock_info": {},
            "source_account": '',
            "result_code": -1,
            "result_reason": "",
            "pay_url": "",
            "raw_order_no": "",
            "expire_datetime": "",
            "pay_money": 0,
        }
        with Bus100Rebot.get_and_lock(order) as rebot:
            is_login = rebot.test_login_status()
            if not is_login:
                lock_result.update(result_code=2,
                                   source_account=rebot.telephone,
                                   result_reason="账号未登陆")
                return lock_result

            try:
                rebot.recrawl_shiftid(order.line)
            except:
                lock_result.update(result_code=2,
                                   source_account=rebot.telephone,
                                   result_reason="源站刷新线路错误，锁票重试")
                return lock_result

            line = Line.objects.get(line_id=order.line.line_id)
            order.line = line
            order.ticket_price = line.full_price
            order.save()

            lock_result.update(source_account=rebot.telephone)
            if order.line.shift_id == "0" or not order.line.extra_info.get('flag', 0):
                lock_result.update(result_reason="该条线路无法购买", result_code=0)
                return lock_result

            ttype, ttpwd = self.request_ticket_info(order, rebot)
            lock_info = self.request_create_order(order, rebot, ttype, ttpwd)
            lock_flag, lock_msg = lock_info["flag"], lock_info.get("msg", "")
            if lock_flag == '0':    # 锁票成功
                expire_datetime = dte.now()+datetime.timedelta(seconds=20*60)
                lock_result.update({
                    "result_code": 1,
                    "lock_info": lock_info,
                    "pay_url": "",
                    "raw_order_no": '',
                    "expire_datetime": expire_datetime,
                    "pay_money": order.order_price,
                })
            elif lock_flag == '2':
                if u'同一出发日期限购6张' in lock_msg:
                    lock_result.update(result_code=2,
                                       source_account="",
                                       result_reason="账号被限购，锁票重试")
                elif u'Could not return the resource to the pool' in lock_msg:
                    lock_result.update(result_code=2,
                                       source_account="",
                                       result_reason="源站系统错误，锁票重试")
                else:
                    lock_result.update(result_code=0,
                                       result_reason=lock_msg)
            elif lock_flag == '99' or u'班次信息错误' in lock_msg:
                lock_result.update(result_code=2,
                                   result_reason=lock_msg)
            else:
                lock_result.update({
                    "result_code": 0,
                    "lock_info": lock_info,
                    "result_reason": lock_msg,
                })
            return lock_result

    def request_ticket_info(self, order, rebot):
        ticketType = u'全票'
        ticketPassword = ''
        url = 'http://www.84100.com/getTrainInfo/ajax'
        data = {
              "shiftId": order.line.shift_id,
              "startId": order.line.s_sta_id,
              "startName": order.line.s_sta_name,
              "ttsId":  ''
        }
        headers = {"User-Agent": rebot.user_agent}
        try:
            trainInfo = requests.post(url, data=data, headers=headers, cookies=rebot.cookies)
            trainInfo = trainInfo.json()
            tickType = trainInfo.get('tickType', '')
            if tickType:
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
        except Exception:
            order_log.info("[lock-result] query trainInfo . order: %s,%s", order.order_no,trainInfo)
        return ticketType, ticketPassword

    def request_create_order(self, order, rebot, ticketType, ticketPassword):
        headers = {"User-Agent": rebot.user_agent}
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
            "startId": order.line.s_sta_id,
            "planId": order.line.shift_id,
            "name": '',#order.contact_info['name'],
            "mobile": '',#order.contact_info['telephone'],
            'smsFlag': '',
            "ticketNo": '',
            "ticketPassword": ticketPassword,
            "idNos": ','.join(idNos),
            "ticketTypes": ','.join(ticketTypes),
            "idTypes": ','.join(idTypes),
            "names": ','.join(names),
        }
        orderInfo = requests.post(url, data=data, headers=headers, cookies=rebot.cookies)
        if orderInfo.status_code == 404:
            return {"flag": "99", "msg": "请求下单页面404"}
        orderInfo = orderInfo.json()
        return orderInfo

    def request_pay_info(self, pay_url):
        r = requests.get(pay_url, verify=False)
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

        rebot = Bus100Rebot.objects.get(telephone=order.source_account)
        tickets = self.send_order_request(order, rebot)
        code_list, msg_list = [], []
        status = tickets.get("status", None)
        if status == '4':
            dx_templ = DUAN_XIN_TEMPL[SOURCE_BUS100]
            ticketPassword = ''
            if tickets.get('ticketPassword', ''):
                ticketPassword = "取票密码:%s;"%tickets.get('ticketPassword', '')
            dx_info = {
                "amount": order.ticket_amount,
                "start": "%s(%s)" % (order.line.s_city_name, order.line.s_sta_name),
                "end": order.line.d_sta_name,
                "time": order.drv_datetime.strftime("%Y-%m-%d %H:%M"),
                "order": tickets["order_id"],
                "ticketPassword": ticketPassword,
            }
            if tickets.get('ticketPassword', ''):
                code_list.append(tickets.get('ticketPassword', ''))
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
        data = {"orderId": order.lock_info['orderId']}
        url = "http://www.84100.com/orderInfo.shtml"
        r = requests.post(url, data=data, cookies=rebot.cookies)
        sel = etree.HTML(r.content)
        orderDetailObj = sel.xpath('//div[@class="ticketInfo"]')

        orderDetail = {}
        if orderDetailObj:
            status = orderDetailObj[0].xpath('div[@class="box02"]/ul/li[4]/span/text()')[0].replace('\r\n','').replace(' ','')
            order_id = orderDetailObj[0].xpath('div[@class="box02"]/ul/li[@class="one"]/span/text()')[0].replace('\r\n','').replace(' ','')
            if order_id:
                if not order.raw_order_no or order.raw_order_no != order_id:
                    order.modify(raw_order_no=order_id)
                orderDetail.update({'order_id': order_id})
                if status == u'正在出票' or status == u'\xe6\xad\xa3\xe5\x9c\xa8\xe5\x87\xba\xe7\xa5\xa8':
                    orderDetail.update({'status': '6'})
                elif status == u"购票成功" or status == u'\xe8\xb4\xad\xe7\xa5\xa8\xe6\x88\x90\xe5\x8a\x9f':
                    orderDetail.update({'status': '4'})
                    ticketPassword = orderDetailObj[0].xpath('//div[@class="check_password"]/input[@id="pswd"]/@value')
                    if ticketPassword:
                        ticketPassword = ticketPassword[0]
                        orderDetail.update({'ticketPassword': ticketPassword})
    #                 matchObj = re.findall('<li>订单号：(.*)', r.content)
    #                 order_id = matchObj[0].replace(' ','')
                elif status == u"订单失效" or status == u'\xe8\xae\xa2\xe5\x8d\x95\xe5\xa4\xb1\xe6\x95\x88' or not status:
                    orderDetail.update({'status': '5'})
        return orderDetail

    def mock_send_order_request(self, order, rebot):
        return {"status": "4", "order_id": "1111111111111"}

    def do_refresh_line(self, line):
        result_info = {
            "result_msg": "",
            "update_attrs": {},
        }
        rebot = None
        for i in Bus100Rebot.objects.filter(is_active=True).order_by('-last_login_time')[0:5]:
            print '1111111111', i.telephone, i.last_login_time
            if i.test_login_status():
                rebot = i
                break
        if not rebot:
            rebot = Bus100Rebot.get_random_rebot()
            data = {
                "loginType": 0,
                "backUrl": '',
                "mobile": rebot.telephone,
                "password": rebot.password,
                "validateCode": '1234'
            }
            r = requests.post("http://84100.com/doLogin/ajax", data=data)
            if r.json().get('flag', '') == '0':
                rebot.modify(cookies=dict(r.cookies), is_active=True, last_login_time=dte.now())
                if not rebot.test_login_status():
                    return result_info
            else:
                return result_info
        now = dte.now()
        rebot.recrawl_shiftid(line)
        line = Line.objects.get(line_id=line.line_id)
        if line.shift_id == "0" or not line.extra_info.get('flag', 0):
            line_log.info("[refresh-result]  no left_tickets line:%s %s ", line.crawl_source, line.line_id)
            result_info.update(result_msg="ok", update_attrs={"left_tickets": 0, "refresh_datetime": now})
            return result_info
        url = "http://www.84100.com/getTrainInfo/ajax"
        payload = {
            "shiftId": line.shift_id,
            "startId": line.s_sta_id,
            "startName": line.s_sta_name,
            "ttsId": ''
        }
        trainInfo = requests.post(url, data=payload, cookies=rebot.cookies)
        trainInfo = trainInfo.json()
        if str(trainInfo['flag']) == '0':
            sel = etree.HTML(trainInfo['msg'])
            full_price = sel.xpath('//div[@class="order_detail"]/div[@class="left"]/p[@class="price"]/em/text()')
            if full_price:
                full_price = float(full_price[0])
            result_info.update(result_msg="ok", update_attrs={"left_tickets": 45, "refresh_datetime": now,'full_price':full_price})
        elif str(trainInfo['flag']) == '1':
            line_log.info("[refresh-result]  no left_tickets line:%s %s,result:%s ", line.crawl_source, line.line_id,trainInfo)
            result_info.update(result_msg="ok", update_attrs={"left_tickets": 0, "refresh_datetime": now})

        return result_info

    def get_pay_page(self, order, valid_code="", session=None, **kwargs):
        if order.source_account:
            rebot = Bus100Rebot.objects.get(telephone=order.source_account)
        else:
            rebot = Bus100Rebot.get_random_rebot()
        if valid_code:      #  登陆
            data = json.loads(session["bus100_pay_login_info"])
            code_url = data["valid_url"]
            headers = data["headers"]
            cookies = data["cookies"]
            data = {
                "loginType": 0,
                "backUrl": '',
                "mobile": rebot.telephone,
                "password": rebot.password,
                "validateCode": valid_code
            }
            r = requests.post("http://84100.com/doLogin/ajax", data=data, headers=headers, cookies=cookies)
            cookies.update(dict(r.cookies))
            rebot.modify(cookies=cookies, is_active=True, last_login_time=dte.now(), user_agent=headers.get("User-Agent", ""))

        is_login = rebot.test_login_status()
        if is_login:
            if order.status == STATUS_LOCK_RETRY:
                self.lock_ticket(order)

            if order.status == STATUS_WAITING_ISSUE:
                url = "http://pay.84100.com/payment/payment/gateWayPay.do"
                params = dict(
                    userIdentifier=rebot.telephone,
                    orderNo=order.lock_info["orderId"],
                    couponId="",
                    payment=5,
                    produceType="",
                )
                headers = {
                    "User-Agent": rebot.user_agent or random.choice(BROWSER_USER_AGENT),
                    "Content-Type": "application/x-www-form-urlencoded",
                }
                r = requests.post(url, headers=headers, cookies=rebot.cookies, data=urllib.urlencode(params), proxies={"http": "http://192.168.1.99:8888"})
                sel = etree.HTML(r.content)
                pay_order_no = sel.xpath("//input[@id='out_trade_no']/@value")[0].strip()
                if order.pay_order_no != pay_order_no:
                    order.update(pay_order_no=pay_order_no)
                return {"flag": "html", "content": r.content}
                #if not order.pay_url:
                #    url = "http://www.84100.com/pay/ajax?orderId=%s" % order.lock_info["orderId"]
                #    headers = {"User-Agent": rebot.user_agent}
                #    r = requests.post(url, headers=headers, cookies=rebot.cookies)
                #    pay_info = r.json()
                #    order.modify(pay_url=pay_info.get('url', ""))
                #if not order.pay_url:
                #    return {"flag": "error", "content": "没有获取到支付连接,请重试!"}
                #return {"flag": "url", "content": order.pay_url}
        else:
            login_form_url = "http://84100.com/login.shtml"
            ua = random.choice(BROWSER_USER_AGENT)
            headers = {"User-Agent": ua}
            r = requests.get(login_form_url, headers=headers)
            sel = etree.HTML(r.content)
            cookies = dict(r.cookies)
            code_url = sel.xpath("//img[@id='validateImg']/@src")[0]
            code_url = 'http://84100.com'+code_url
            r = requests.get(code_url, headers=headers, cookies=cookies)
            cookies.update(dict(r.cookies))
            data = {
                "cookies": cookies,
                "headers": headers,
                "valid_url": code_url,
            }
            session["bus100_pay_login_info"] = json.dumps(data)
            return {"flag": "input_code", "content": ""}
