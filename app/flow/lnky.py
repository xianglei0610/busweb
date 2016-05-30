#!/usr/bin/env python
# encoding: utf-8

import requests
import json
import urllib
import re

import datetime
import random
from lxml import etree

from app.constants import *
from app.flow.base import Flow as BaseFlow
from app.models import LnkyWapRebot, Line, Order, LnkyWebRebot
from datetime import datetime as dte
from app import order_log, line_log
from app.utils import md5


class Flow(BaseFlow):

    name = "lnky"

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
        if not self.check_wap_status():
            return self.do_lock_ticket_by_web(order)
        with LnkyWapRebot.get_and_lock(order) as rebot:
            if not rebot.test_login_status():
                rebot.login()
                rebot.reload()
            line = order.line
            res = self.send_lock_request(order, rebot)
            lock_result.update({
                "lock_info": res,
                "source_account": rebot.telephone,
                "pay_money": line.real_price()*order.ticket_amount,
            })
            today = datetime.date.today()
            check_str = str(today).replace('-', '')
            if check_str in res['msg']:
                order_no = res['msg'][1:-1]
                expire_time = dte.now()+datetime.timedelta(seconds=60*40)
                lock_result.update({
                    "result_code": 1,
                    "result_reason": "",
                    "pay_url": '',
                    "raw_order_no": order_no,
                    "expire_datetime": expire_time,
                    "lock_info": res
                })
            else:
                errmsg = res['msg']
                if "404" in errmsg:
                    lock_result.update({
                        "result_code": 2,
                        "source_account": rebot.telephone,
                        "result_reason": str(rebot.telephone) + ':' + res["msg"],
                    })
                    return lock_result
                if "E008" in errmsg:
                    rebot = order.change_lock_rebot()
                    lock_result.update({
                        "result_code": 2,
                        "source_account": rebot.telephone,
                        "result_reason": str(rebot.telephone) + res["msg"],
                    })
                    return lock_result
                for s in ["E015", "E001"]: #余票不足
                    if s in errmsg:
                        self.close_line(line, reason=errmsg)
                        break
                lock_result.update({
                    "result_code": 0,
                    "result_reason": res,
                    "pay_url": "",
                    "raw_order_no": "",
                    "expire_datetime": None,
                })
            return lock_result

    def do_lock_ticket_by_web(self, order):
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
        with LnkyWebRebot.get_and_lock(order) as rebot:
            rebot.login()
            rebot.reload()
            cookies = json.loads(rebot.cookies)
            headers = rebot.http_header()
            line = order.line
            depotId = self.query_station_depotId_by_web(rebot, order, cookies, headers)
            res = self.send_lock_request_by_web(rebot, order, cookies, headers,depotId)
            lock_result.update({
                "lock_info": res,
                "source_account": rebot.telephone,
                "pay_money": line.real_price()*order.ticket_amount,
            })
            today = datetime.date.today()
            check_str = str(today).replace('-', '')
            if check_str in res['msg']:
                order_no = res['msg'][1:-1]
                expire_time = dte.now()+datetime.timedelta(seconds=60*40)
                lock_result.update({
                    "result_code": 1,
                    "result_reason": "",
                    "pay_url": res.get('pay_url', ''),
                    "raw_order_no": order_no,
                    "expire_datetime": expire_time,
                    "lock_info": res
                })
            else:
                errmsg = res['msg']
                if "404" in errmsg:
                    lock_result.update({
                        "result_code": 2,
                        "source_account": rebot.telephone,
                        "result_reason": str(rebot.telephone) + ':' + res["msg"],
                    })
                    return lock_result
                if "E008" in errmsg:
                    rebot = order.change_lock_rebot()
                    lock_result.update({
                        "result_code": 2,
                        "source_account": rebot.telephone,
                        "result_reason": str(rebot.telephone) + res["msg"],
                    })
                    return lock_result
                for s in ["E015", "E001"]: #余票不足
                    if s in errmsg:
                        self.close_line(line, reason=errmsg)
                        break
                lock_result.update({
                    "result_code": 0,
                    "result_reason": errmsg,
                    "pay_url": "",
                    "raw_order_no": "",
                    "expire_datetime": None,
                })
            return lock_result

    def query_station_depotId_by_web(self, rebot, order, cookies, headers):
        line = order.line
        line_url = 'http://www.jt306.cn/ticket/it/search.action'
        data = {
                "arrival": line.d_sta_name,
                "beginStation": line.s_sta_name,
                "randome": "".join(random.sample("0123456789abcdefghijklmnopqrstuvwxzy",4)),
                "startTimeValue": "0",
                "travelDate":  line.drv_date,
                "type": "1",
                }
        r = requests.post(url=line_url, data=data, cookies=cookies, headers=headers)
        content = r.content
        matchObj = re.findall('depotId=(.*)&', content)
        depotId = matchObj[0]
        return depotId

    def send_lock_request(self, order, rebot):
        """
        单纯向源站发请求
        """
        line = order.line
        riders = order.riders
        tickets = []
        for i in riders:
            lst = [str(line.full_price), i['id_number'], i['name'], "全", i['telephone']]
            tickets.append("::".join(lst))
        data = {
                "arrival": line.d_sta_name,
                "departureStation": line.s_sta_name,
                "tickets": "@@".join(tickets),
                "trainnumber": line.bus_num,
                "travelDate": line.drv_date,
                "travelTime": line.drv_time,
                }
        order_url = "http://www.jt306.cn/wap/ticketSales/ajaxMakeOrder.do"
        headers = rebot.http_header()
        line = order.line
        r = rebot.http_post(order_url, data=data, headers=headers, cookies=json.loads(rebot.cookies),timeout=40)
        ret = r.content
        if ret == '404':
            unpay_all_order = "http://www.jt306.cn/wap/userCenter/ajaxGetOrders.do"
            data = {
                    "status": "1",
                    "timeStatus": "1"
                    }
            r = rebot.http_post(unpay_all_order, data=data, headers=headers, cookies=json.loads(rebot.cookies))
            content = r.content
            if content != '404':
                res = r.json()
                if res['resultCode'] == '0000':
                    for i in res['pageData']:
                        if i['status']=='0' and i['startTime']==line.drv_time and i['startDate'] == line.drv_date \
                             and i['price']==str(line.full_price) and i['startStationName']==line.s_sta_name and i['endStationName']==line.d_sta_name:
                            count = Order.objects.filter(raw_order_no=i['orderNo']).count()
                            if count == 0:
                                ret = i['orderNo']
                                break
        return {'flag': True, 'msg': ret}

    def send_lock_request_by_web(self, rebot, order, cookies, headers, depotId):
        riders = order.riders
        line = order.line
        tickets = []
        for i in riders:
            lst = ["全", i['name'], "二代身份证",i['id_number'], i['telephone']]
            tickets.append("::".join(lst))
        params = {
                "orders.fare": line.real_price()*order.ticket_amount,
                "psgString": "@@".join(tickets),
                "userId": rebot.user_id
                 }
        url = "http://www.jt306.cn/ticket/it/createOrder.action"
        order_url = "%s?%s" % (url, urllib.urlencode(params))
        data = {
            "orders.station": depotId,
            "orders.arrive": line.d_sta_name,
            "orders.beginstation": line.s_sta_name,
            "orders.cartype": "",
            "orders.drivetime": line.drv_time,
            "orders.highway": "",
            "orders.runs": line.bus_num,
            "orders.line": "",
            "orders.mileage": "",
            "orders.runtime": "",
            "orders.ridingdate": line.drv_date,
            "orders.traintype": "",
            "orders.resCompany": "",
            "orders.via": line.d_city_name
        }

        res = rebot.http_post(order_url, data=data, cookies=cookies, headers=headers)
        content = res.content
        if not isinstance(content, unicode):
            content = content.decode('utf-8')
        sel = etree.HTML(content)
        pay_url = sel.xpath('//form[@id="payForm"]/@action')
        state_error = sel.xpath('//form[@name="oJumpForm"]/p[@class="ui-state-error"]/text()')
        if state_error:
            return {'flag': True, 'msg': state_error[0]}
        if pay_url:
            order_no = sel.xpath('//div[@class="pay-left"]/table[@class="pay-table"]/tr[1]/td[2]/text()')
            order_no = order_no[0]
            pay_url = pay_url[0]
            return {'flag': True, 'msg': order_no, "pay_url":pay_url}

    def send_orderDetail_request(self, rebot, order=None, lock_info=None):
        cookies = json.loads(rebot.cookies)
        detail_url = "http://www.jt306.cn/wap/ticketSales/makeOrder.do?orderNo=%s"%order.raw_order_no
        headers = rebot.http_header()
        r = rebot.http_get(detail_url, headers=headers, cookies=cookies)
        content = r.content
        if not isinstance(content, unicode):
            content = content.decode('utf-8')
        sel = etree.HTML(r.content)
        orderDetail = sel.xpath('//div[@id="orderDetailJson"]/text()')
        if orderDetail:
            orderDetailArr = json.loads(orderDetail[0])
            orderDetail = orderDetailArr[0]
            if orderDetail['status'] == '0':
                if int(orderDetail['paySeconds']) <= 0:
                    return {"state": u'订单超时'}
                pay_url = orderDetail['payURL']
                order.modify(pay_url=pay_url)
                order.reload()
                return {"state": u'等待付款'}
            elif orderDetail['status'] == '1':
                return {"state": u"购票成功"}

    def send_orderDetail_request_by_web(self, rebot, order):
        cookies = json.loads(rebot.cookies)
        detail_url = 'http://www.jt306.cn/ticket/o/print.action?printOrderNo=%s&userId=%s'%(order.raw_order_no, rebot.user_id)
        data = {
               "orderNo": order.raw_order_no,
               "runs": '',
               "select": '0',
               "startDate": str(datetime.date.today()+datetime.timedelta(days=-1)),
               "endDate": str(datetime.date.today()+datetime.timedelta(days=1))
               }
        headers = rebot.http_header()
        r = rebot.http_post(detail_url, data=data, headers=headers, cookies=cookies)
        content = r.content
        if not isinstance(content, unicode):
            content = content.decode('utf-8')
        sel = etree.HTML(content)
        orderDetail = sel.xpath('//div[@class="d-tail-table"]/table/tr[2]/td[8]/text()')
        if orderDetail:
            orderDetail = orderDetail[0].replace('\r', '').replace('\t','').replace('\n','').replace(' ','')
            if orderDetail == u'已支付':
                return {"state": u"购票成功"}
            else:
                return {"state": u'等待付款'}

    def do_refresh_issue(self, order):
        result_info = {
            "result_code": 0,
            "result_msg": "",
            "pick_code_list": [],
            "pick_msg_list": [],
        }
        ret = {}
        if self.check_wap_status():
            rebot = LnkyWapRebot.objects.get(telephone=order.source_account)
            if not rebot.test_login_status():
                rebot.login()
                rebot.reload()
            ret = self.send_orderDetail_request(rebot, order=order)
        else: #query order by pc.
            rebot = LnkyWebRebot.objects.get(telephone=order.source_account)
            if not rebot.test_login_status():
                rebot.login()
                rebot.reload()
            ret = self.send_orderDetail_request_by_web(rebot, order=order)
        state = ret["state"]
        order_status_mapping = {
                u"购票成功": "出票成功",
                u"订单超时": "出票失败",
                u'等待付款': "等待付款",
                }
        if state in(u"购票成功"): #"出票成功":
            code_list = []
            msg_list = []
            dx_templ = DUAN_XIN_TEMPL[SOURCE_LNKY]
            dx_info = {
                "start": "%s(%s)" % (order.line.s_city_name, order.line.s_sta_name),
                "end": order.line.d_sta_name,
                "time": order.drv_datetime.strftime("%Y-%m-%d %H:%M"),
                "order_no": order.raw_order_no,
                "ticket_amount": order.ticket_amount,
            }
            code_list.append('无需取票密码')
            msg_list.append(dx_templ % dx_info)
            result_info.update({
                "result_code": 1,
                "result_msg": order_status_mapping[state],
                "pick_code_list": code_list,
                "pick_msg_list": msg_list,
            })
        elif state in("出票中"): #"出票中":
            result_info.update({
                "result_code": 4,
                "result_msg": order_status_mapping[state],
            })
        elif state in (u"订单超时"):#取消购票,购票失败,退票成功
            result_info.update({
                "result_code": 2,
                "result_msg": order_status_mapping[state],
            })
        return result_info

    def check_wap_status(self):
        return 0
        try:
            rebot = LnkyWapRebot.get_one()
            headers = rebot.http_header()
            if headers.has_key('Content-Type'):
                del headers['Content-Type']
            url = "http://www.jt306.cn/wap/login/home.do"
            res = rebot.http_get(url, headers=headers)
            content = res.content
            if res.status_code == '404' or content == '404':
                return 0
            else:
                return 1
        except:
            return 0

    def get_pay_page(self, order, valid_code="", session=None, pay_channel="alipay" ,**kwargs):
        flag = self.check_wap_status()
        if flag:
            rebot = LnkyWapRebot.objects.get(telephone=order.source_account)
        else:
            try:
                rebot = LnkyWebRebot.objects.get(telephone=order.source_account)
            except:
                rebot = LnkyWebRebot.get_one()

        def _get_page(rebot):
            if order.status == STATUS_WAITING_ISSUE:
                headers = rebot.http_header()
                cookies = json.loads(rebot.cookies)
                if flag:
                    detail_url = "http://www.jt306.cn/wap/ticketSales/makeOrder.do?orderNo=%s"%order.raw_order_no
                    headers = rebot.http_header()
                    r = rebot.http_get(detail_url, headers=headers, cookies=cookies)
                    content = r.content
                    if not isinstance(content, unicode):
                        content = content.decode('utf-8')
                    sel = etree.HTML(r.content)
                    orderDetail = sel.xpath('//div[@id="orderDetailJson"]/text()')
                    if orderDetail:
                        orderDetailArr = json.loads(orderDetail[0])
                        orderDetail = orderDetailArr[0]
                        if orderDetail['status'] == '0':
                            if int(orderDetail['paySeconds']) <= 0:
                                return {"flag": "false", "content": '订单超时'}
                            pay_url = orderDetail['payURL']
                        elif orderDetail['status'] == '1':
                            return {"flag": "false", "content": '订单已经支付'}
                        else:
                            return {"flag": "false", "content": '订单不是待支付的状态'}
                else:
                    pay_url = order.lock_info.get("pay_url", '')
                if not pay_url:
                    return {"flag": "error", "content": "没有获取到支付连接,请重试!"}
                r = requests.get(pay_url, headers=headers, cookies=cookies)
                sel = etree.HTML(r.content)
                params = {}
                for s in sel.xpath("//form[@id='bankPayForm']//input"):
                    k, v = s.xpath("@name"), s.xpath("@value")
                    k, v = k[0], v[0] if v else ""
                    params[k] = v
                if not params and pay_url:
                    return {"flag": "url", "content": pay_url}
                url = "http://61.161.205.217/payment/payment/gotoChinaPay.do"
                r = requests.post(url, headers=headers, cookies=cookies, data=urllib.urlencode(params))
                sel = etree.HTML(r.content)
                pay_order_no = sel.xpath("//input[@name='OrdId']/@value")[0].strip()
                if order.pay_order_no != pay_order_no:
                    order.update(pay_order_no=pay_order_no)
                return {"flag": "html", "content": r.content}
            return {"flag": "error", "content": "锁票失败"}
        is_login = rebot.test_login_status()
        if not is_login:
            rebot.login()
            rebot.reload()
        if order.status in [STATUS_LOCK_RETRY, STATUS_WAITING_LOCK]:
            self.lock_ticket(order)
        return _get_page(rebot)

    def do_refresh_line(self, line):
        result_info = {
            "result_msg": "",
            "update_attrs": {},
        }
        now = dte.now()
        ua = random.choice(MOBILE_USER_AGENG)
        headers = {"User-Agent": ua}
        line_url = "http://www.jt306.cn/wap/ticketSales/ticketList.do"
        payload = {
            "endCityName": line.d_city_name,
            "startCityName": line.s_city_name,
            "startDate": line.drv_date
                }
        try:
            r = requests.post(line_url, data=payload, headers=headers, timeout=10)
        except:
            result_info.update(result_msg="timeout default 20", update_attrs={"left_tickets": 20, "refresh_datetime": now})
            return result_info
        content = r.content
        if not isinstance(content, unicode):
            content = content.decode('utf-8')
        sel = etree.HTML(content)
        scheduleInfo = sel.xpath('//input[@id="scheduleInfoJson"]/@value')
        update_attrs = {}
        if scheduleInfo:
            scheduleInfo = json.loads(scheduleInfo[0])
            for d in scheduleInfo:
                if not isinstance(d, dict):
                    continue
                drv_datetime = dte.strptime("%s %s" % (line.drv_date, d["driveTime"]), "%Y-%m-%d %H:%M")
                line_id_args = {
                    "s_city_name": line.s_city_name,
                    "d_city_name": line.d_city_name,
                    "bus_num": d['trainNumber'],
                    "crawl_source": line.crawl_source,
                    "drv_datetime": drv_datetime,
                }
                line_id = md5("%(s_city_name)s-%(d_city_name)s-%(drv_datetime)s-%(bus_num)s-%(crawl_source)s" % line_id_args)
                try:
                    obj = Line.objects.get(line_id=line_id)
                except Line.DoesNotExist:
                    continue
                info = {
                    "full_price": float(d["price"]),
                    "fee": 0,
                    "left_tickets": int(d['seatLast']),
                    "refresh_datetime": now,
                }
                if line_id == line.line_id:
                    update_attrs = info
                else:
                    info.update({"s_sta_name": d['fromStation']})
                    obj.update(**info)
        if not update_attrs:
            result_info.update(result_msg="no line info", update_attrs={"left_tickets": 0, "refresh_datetime": now})
        else:
            result_info.update(result_msg="ok", update_attrs=update_attrs)
        return result_info
