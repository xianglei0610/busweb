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
from app.models import XinTuYunWebRebot, Line
from app import order_log, line_log


class Flow(BaseFlow):
    name = "xintuyun"

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
        with XinTuYunWebRebot.get_and_lock(order) as rebot:
            is_login = rebot.test_login_status()
            if not is_login:
                rebot.login()
            try:
                rebot.recrawl_shiftid(order.line)
            except:
                lock_result.update(result_code=2,
                                   source_account=rebot.telephone,
                                   result_reason="源站刷新线路错误，锁票重试")
                return lock_result

            line = Line.objects.get(line_id=order.line.line_id)
            order.modify(line=line)

            lock_result.update(source_account=rebot.telephone)
            if order.line.shift_id == "0" or not order.line.extra_info.get('flag', 0):
                lock_result.update(result_reason="该条线路无法购买", result_code=0)
                return lock_result

            ttype, ttpwd = self.request_ticket_info(order, rebot)
            lock_info = self.request_create_order(order, rebot, ttype, ttpwd)
            order_log.info("[lock-result]  request_create_order . order: %s,account:%s,result:%s", order.order_no,rebot.telephone,lock_info)
            lock_flag, lock_msg = lock_info["flag"], lock_info.get("msg", "")
            if u"乘车人不能超过" in lock_msg:
                order.line.shift_id = "0"
                order.save()
                lock_result.update(result_code=0,
                                   result_reason=lock_msg)
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
                    new_rebot = order.change_lock_rebot()
                    lock_result.update(result_code=2,
                                       source_account=new_rebot.telephone,
                                       result_reason="账号被限购，锁票重试")
                elif u'Could not return the resource to the pool' in lock_msg:
                    lock_result.update(result_code=2,
                                       source_account="",
                                       result_reason="源站系统错误，锁票重试")
                else:
                    for s in [u'班次信息错误',u'该条线路无法购买',u"余票不足",u"剩余座位数不足",u"获取座位信息失败",u"没有可售的座位"]:
                        if s in lock_msg:
                            self.close_line(line, reason=lock_msg)
                            break
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
        ticketType = u'全'
        ticketPassword = ''
        headers = rebot.http_header()
        cookies = json.loads(rebot.cookies)
        url = 'http://www.xintuyun.cn/getTrainInfo/ajax'
        data = {
              "shiftId": order.line.shift_id,
              "startId": order.line.s_sta_id,
              "startName": order.line.s_sta_name,
              "ttsId":  ''
        }
        try:
            trainInfo = requests.post(url, data=data, headers=headers, cookies=cookies)
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
        headers = rebot.http_header()
        cookies = json.loads(rebot.cookies)
        url = 'http://www.xintuyun.cn/createOrder/ajax'
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
        orderInfo = rebot.http_post(url, data=data, headers=headers, cookies=cookies)
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

        rebot = XinTuYunWebRebot.objects.get(telephone=order.source_account)
        if not rebot.test_login_status():
            rebot.login()
        ret = self.send_order_request(order, rebot)
        code_list, msg_list = [], []
        status = ret.get("status", None)
        order_status_mapping = {
                u"购票成功": "购票成功",
                u"订单失效": "订单失效",
                u'正在出票': "正在出票",
                }
        if status in (u"购票成功"):
            dx_templ = DUAN_XIN_TEMPL[SOURCE_XINTUYUN]
            ticketPassword = ''
            if ret.get('ticketPassword', ''):
                ticketPassword = "取票密码:%s;"%ret.get('ticketPassword', '')
            dx_info = {
                "amount": order.ticket_amount,
                "start": "%s(%s)" % (order.line.s_city_name, order.line.s_sta_name),
                "end": order.line.d_sta_name,
                "time": order.drv_datetime.strftime("%Y-%m-%d %H:%M"),
                "order": ret["order_id"],
                "ticketPassword": ticketPassword,
            }
            if ret.get('ticketPassword', ''):
                code_list.append(ret.get('ticketPassword', ''))
            else:
                code_list.append('无需取票密码')
            msg_list.append(dx_templ % dx_info)
            result_info.update({
                "result_code": 1,
                "result_msg": "",
                "pick_code_list": code_list,
                "pick_msg_list": msg_list,
            })
        elif status in (u"正在出票"):
            result_info.update({
                "result_code": 4,
                "result_msg": order_status_mapping[status],
            })
        elif status in (u"订单失效"):
            result_info.update({
                "result_code": 2,
                "result_msg": order_status_mapping[status],
            })
        return result_info

    def send_order_request(self, order, rebot):
        data = {"orderId": order.lock_info['orderId']}
        url = "http://www.xintuyun.cn/orderInfo.shtml"
        headers = rebot.http_header()
        cookies = json.loads(rebot.cookies)
        r = requests.post(url, data=data, headers=headers,cookies=cookies)
        content = r.content
        if not isinstance(content, unicode):
            content = content.decode('utf-8')
        sel = etree.HTML(content)
        orderDetailObj = sel.xpath('//div[@class="ticketInfo"]')

        orderDetail = {}
        if orderDetailObj:
            status = orderDetailObj[0].xpath('div[@class="box02"]/ul/li[4]/span/text()')[0].replace('\r\n','').replace(' ','')
            order_id = orderDetailObj[0].xpath('div[@class="box02"]/ul/li[@class="one"]/span/text()')[0].replace('\r\n','').replace(' ','')
            orderDetail.update({'status': status})
            if order_id:
                if not order.raw_order_no or order.raw_order_no != order_id:
                    order.modify(raw_order_no=order_id)
                orderDetail.update({'order_id': order_id})
#                 if status == u'正在出票':
#                     orderDetail.update({'status': '6'})
                if status == u"购票成功":
                    ticketPassword = orderDetailObj[0].xpath('//div[@class="check_password"]/input[@id="pswd"]/@value')
                    if ticketPassword:
                        ticketPassword = ticketPassword[0]
                        orderDetail.update({'ticketPassword': ticketPassword})
    #                 matchObj = re.findall('<li>订单号：(.*)', r.content)
    #                 order_id = matchObj[0].replace(' ','')
#                 elif status == u"订单失效" or not status:
#                     orderDetail.update({'status': '5'})
        return orderDetail

    def do_refresh_line(self, line):
        result_info = {
            "result_msg": "",
            "update_attrs": {},
        }
        rebot = XinTuYunWebRebot.get_one()
        if not rebot.test_login_status():
            rebot.login()
        now = dte.now()
        if line.shift_id == "0" or not line.extra_info.get('flag', 0):
            line_log.info("[refresh-result]  no left_tickets line:%s %s ", line.crawl_source, line.line_id)
            result_info.update(result_msg="no left_tickets line", update_attrs={"left_tickets": 0, "refresh_datetime": now})
            return result_info
        try:
            is_exist = rebot.recrawl_shiftid(line)
        except:
            result_info.update(result_msg="no line info", update_attrs={"left_tickets": 0, "refresh_datetime": now})
        line.reload()
        if not is_exist:
            line.modify(left_tickets=0)
        result_info.update(result_msg="ok", update_attrs={"left_tickets": line.left_tickets, "refresh_datetime": now,'full_price':line.full_price})
#         url = "http://www.xintuyun.cn/getTrainInfo/ajax"
#         payload = {
#             "shiftId": line.shift_id,
#             "startId": line.s_sta_id,
#             "startName": line.s_sta_name,
#             "ttsId": ''
#         }
#         trainInfo = requests.post(url, data=payload, cookies=rebot.cookies)
#         if trainInfo.status_code == 404:
#             line_log.info("[refresh-result] request 404 line:%s,%s %s ", line.crawl_source,line.s_city_name, line.line_id)
#             result_info.update(result_msg="ok", update_attrs={"left_tickets": 0, "refresh_datetime": now})
#         else:
#             trainInfo = trainInfo.json()
#             if str(trainInfo['flag']) == '0':
#                 sel = etree.HTML(trainInfo['msg'])
#                 full_price = sel.xpath('//div[@class="order_detail"]/div[@class="left"]/p[@class="price"]/em/text()')
#                 if full_price:
#                     full_price = float(full_price[0])
#                 try:
#                     ticket_info = sel.xpath('//div[@class="order_detail"]/div[@class="right"]/p[3]/a/text()')[0]
#                     p = re.compile(r'\d+')
#                     left_ticketObj = p.findall(ticket_info)
#                     left_tickets = 0
#                     if left_ticketObj:
#                         left_tickets = int(left_ticketObj[0])
#                     if int(trainInfo['maxSellNum']) < 3:
#                         left_tickets = 0
#                 except Exception, e:
#                     line_log.info("[refresh-result] request error line:%s,%s %s,%s ", line.crawl_source,line.s_city_name, line.line_id,e)
#                     left_tickets = 0
#
#                 result_info.update(result_msg="ok", update_attrs={"left_tickets": left_tickets, "refresh_datetime": now,'full_price':full_price})
#             elif str(trainInfo['flag']) == '1':
#                 line_log.info("[refresh-result]  no left_tickets line:%s,%s %s,result:%s ", line.crawl_source,line.s_city_name, line.line_id,trainInfo)
#                 result_info.update(result_msg="ok", update_attrs={"left_tickets": 0, "refresh_datetime": now})

        return result_info

    def get_pay_page(self, order, valid_code="", session=None, **kwargs):
        if order.source_account:
            rebot = XinTuYunWebRebot.objects.get(telephone=order.source_account)
        else:
            rebot = XinTuYunWebRebot.get_one()
        is_login = rebot.test_login_status()
        if not is_login and valid_code:      #  登陆
            key = "pay_login_info_%s_%s" % (order.order_no, order.source_account)
            data = json.loads(session[key])
            code_url = data["valid_url"]
            headers = data["headers"]
            cookies = data["cookies"]
            msg = rebot.login(valid_code=valid_code, headers=headers, cookies=cookies)
            if msg == "OK":
                is_login = True
                rebot.modify(cookies=json.dumps(cookies))
        if is_login:
            if order.status in (STATUS_WAITING_LOCK, STATUS_LOCK_RETRY):
                self.lock_ticket(order)

            if order.status == STATUS_WAITING_ISSUE:
                headers = rebot.http_header()
                headers.update({"X-Requested-With": "XMLHttpRequest"})
                cookies = json.loads(rebot.cookies)
                if not order.pay_url:   # 生成支付链接
                    url = "http://www.xintuyun.cn/getPayUrl/ajax?orderId=%s" % order.lock_info["orderId"]
                    r = rebot.http_post(url, data={}, headers=headers, cookies=cookies)      # 这步不能删
                    pay_info = r.json()
                    order.modify(pay_url=pay_info.get('url', ""))

                r = rebot.http_get(order.pay_url, headers=headers, cookies=cookies)
                sel = etree.HTML(r.content)
                params = {}
                for s in sel.xpath("//form[@id='alipayForm']//input"):
                    k, v = s.xpath("@name"), s.xpath("@value")
                    k, v = k[0], v[0] if v else ""
                    if k == "payment":
                        v = "15"
                    params[k] = v

                if not params and order.pay_url:
                    return {"flag": "url", "content": order.pay_url}
                url = "http://pay.xintuyun.cn/payment/payment/gateWayPay.do"
                r = requests.post(url, headers=headers, cookies=cookies, data=urllib.urlencode(params))
                sel = etree.HTML(r.content)
                pay_order_no = sel.xpath("//input[@id='out_trade_no']/@value")[0].strip()
                if order.pay_order_no != pay_order_no:
                    order.update(pay_order_no=pay_order_no)
                return {"flag": "html", "content": r.content}

#                 if not order.pay_url:
#                     url = "http://www.84100.com/pay/ajax?orderId=%s" % order.lock_info["orderId"]
#                     headers = {"User-Agent": rebot.user_agent}
#                     r = requests.post(url, headers=headers, cookies=rebot.cookies)
#                     pay_info = r.json()
#                     order.modify(pay_url=pay_info.get('url', ""))
#                 if not order.pay_url:
#                     return {"flag": "error", "content": "没有获取到支付连接,请重试!"}
#                 return {"flag": "url", "content": order.pay_url}
        else:
            login_form_url = "http://www.xintuyun.cn/login.shtml"
            ua = random.choice(BROWSER_USER_AGENT)
            headers = {"User-Agent": ua}
            r = requests.get(login_form_url, headers=headers)
            sel = etree.HTML(r.content)
            cookies = dict(r.cookies)
            code_url = sel.xpath("//img[@id='validateImg']/@src")[0]
            code_url = 'http://www.xintuyun.cn'+code_url
            r = requests.get(code_url, headers=headers, cookies=cookies)
            cookies.update(dict(r.cookies))
            data = {
                "cookies": cookies,
                "headers": headers,
                "valid_url": code_url,
            }
            key = "pay_login_info_%s_%s" % (order.order_no, order.source_account)
            session[key] = json.dumps(data)
            return {"flag": "input_code", "content": ""}
