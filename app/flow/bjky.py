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
from app.models import BjkyWebRebot, Line
from datetime import datetime as dte
from app import order_log, line_log
from app.utils import md5


class Flow(BaseFlow):

    name = "bjky"

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
        rebot = order.get_lock_rebot()
        if not rebot.test_login_status():
            lock_result.update(result_code=2,
                                source_account=rebot.telephone,
                                result_reason="账号未登陆")
            return lock_result
        self.request_select_schedule(order, rebot)
        try:
            shopcartct = self.request_query_shopcart(rebot)
        except:
            rebot.modify(ip="")
            rebot.modify(cookies="{}")
            lock_result.update(result_code=2,
                                source_account=rebot.telephone,
                                result_reason="查询购物车1异常")
            return lock_result
        if shopcartct != '0':
            self.request_clear_shopcart(rebot)
        errmsg = self.request_add_shopcart(order, rebot)
        if errmsg:
            if "您今天可购票数" in errmsg[0]:
                rebot.modify(cookies="{}")
                rebot = order.change_lock_rebot()
                lock_result.update(result_code=2,
                                    source_account=rebot.telephone,
                                    result_reason="可购票数超过了")
                return lock_result
            if "购物车中已经存在发车日期" in errmsg[0]:
                self.request_clear_shopcart(rebot)
            elif errmsg:
                if "余票数不足" in errmsg[0]:
                    self.close_line(order.line, reason=errmsg)
                lock_result.update(result_code=0,
                                    source_account=rebot.telephone,
                                    result_reason='add_shopcart1'+errmsg[0],
                                    lock_info={'result_reason': errmsg[0]})
                return lock_result
        shopcartct = self.request_query_shopcart(rebot)
        if shopcartct == '0':
            errmsg = self.request_add_shopcart(order, rebot)
            if errmsg:
                lock_result.update(result_code=0,
                                    source_account=rebot.telephone,
                                    result_reason='add_shopcart2'+errmsg[0],
                                    lock_info={'result_reason': errmsg[0]})
                return lock_result
        if int(shopcartct) != len(order.riders):
            rebot.modify(ip="")
            rebot.modify(cookies="{}")
            new_rebot = order.change_lock_rebot()
            lock_result.update(result_code=2,
                                source_account=new_rebot.telephone,
                                result_reason=rebot.telephone+":购物车中数量和购票人数不相同")
            return lock_result
        try:
            res = self.request_create_order(order, rebot)
        except Exception, e:
            order_log.info("[lock-error] order: %s,account:%s lock request error %s", order.order_no, rebot.telephone,e)
            res = self.request_create_order(order, rebot)
        if res['order_no']:
            res['order_no'] = res['order_no'][0]
            res['order_id'] = res['pay_url'][0].split('/')[-1]
        lock_result = {
            "lock_info": res,
            "source_account": rebot.telephone,
            "pay_money": order.line.real_price()*order.ticket_amount,
        }
        if res['order_no']:
            order_no = res['order_no']
            expire_time = dte.now()+datetime.timedelta(seconds=60*24)
            lock_result.update({
                "result_code": 1,
                "result_reason": "",
                "pay_url": '',
                "raw_order_no": order_no,
                "expire_datetime": expire_time,
                "lock_info": res
            })
        else:
            lock_result.update({
                "result_code": 0,
                "result_reason": res,
                "pay_url": "",
                "raw_order_no": "",
                "expire_datetime": None,
            })
        return lock_result

    def request_select_schedule(self, order, rebot):
        line = order.line
        headers = rebot.http_header()
        cookies = json.loads(rebot.cookies)
        data = {
                "ScheduleString": line.extra_info['ScheduleString'],
                "StopString": line.extra_info['ArrivingStopJson']
                }
        select_url = "http://e2go.com.cn/TicketOrder/SelectSchedule"
        r = rebot.http_post(select_url, data=data, headers=headers, cookies=cookies)
        cookies.update(dict(r.cookies))
        ret = r.content
        rebot.modify(cookies=json.dumps(cookies))
        rebot.reload()

    def request_add_shopcart(self, order, rebot):
        riders = order.riders
        headers = rebot.http_header()
        cookies = json.loads(rebot.cookies)
        add_shopcart_url = 'http://e2go.com.cn/TicketOrder/AddScheduleTicket'
        errmsg = ''
        for i in riders:
            data = {
                "AddToTicketOwnerList": "false",
                "CredentialNO": i['id_number'],
                'CredentialType': "Identity",
                "PassengerName": i['name'],
                "SelectedSchedule": '',
                "SelectedStop": '',
                "SellInsurance": "false",
                "WithChild": "false",
            }
            r = rebot.http_post(add_shopcart_url, data=data, headers=headers, cookies=cookies)
            ret = r.content
            if not isinstance(ret, unicode):
                ret = ret.decode('utf-8')
            sel = etree.HTML(ret)
            errmsg = sel.xpath('//*[@id="addOneTicket"]/ul/li[2]/div[3]/span/text()')
        return errmsg

    def request_query_shopcart(self, rebot):
        headers = rebot.http_header()
        cookies = json.loads(rebot.cookies)
        url = "http://e2go.com.cn/TicketOrder/ShoppingCart"
        r = rebot.http_get(url, headers=headers, cookies=cookies)
        ret = r.content
        if not isinstance(ret, unicode):
            ret = ret.decode('utf-8')
        sel = etree.HTML(ret)
        shopinfo = sel.xpath('//*[@id="shoppingCartInfo"]/div[1]/b[1]/text()')[0]
        shopcartct = shopinfo.replace('\r\n', '').replace('\t', '').replace(' ', '')
        return shopcartct

    def request_clear_shopcart(self, rebot):
        headers = rebot.http_header()
        cookies = json.loads(rebot.cookies)
        clear_url = 'http://e2go.com.cn/TicketOrder/ClearShoppingCart'
        r = rebot.http_get(clear_url, headers=headers, cookies=cookies)
        ret = r.content
        if not isinstance(ret, unicode):
            ret = ret.decode('utf-8')
        sel = etree.HTML(ret)
        shopinfo = sel.xpath('//*[@id="shoppingCartInfo"]/div[1]/b[1]/text()')[0]
        shopcartct = shopinfo.replace('\r\n', '').replace('\t', '').replace(' ', '')
        return shopcartct

    def request_create_order(self, order, rebot):
        headers = rebot.http_header()
        cookies = json.loads(rebot.cookies)
        order_url = 'http://e2go.com.cn/TicketOrder/Order'
        r = rebot.http_post(order_url, headers=headers, cookies=cookies)
        content = r.content
        if not isinstance(content, unicode):
            content = content.decode('utf-8')
        sel = etree.HTML(content)
        order_no = sel.xpath('//div[@class="orderContainer"]/div[@class="importantBox orderTip"]/strong/text()')
        pay_url = sel.xpath('//a[@id="payLink"]/@href')
        res = {"order_no": order_no, 'pay_url': pay_url}
        return res

    def send_orderDetail_request(self, rebot, order=None, lock_info=None):
        rebot.modify(ip="")     # 解决代理ip缓存结果的问题
        order_detail_url = "http://e2go.com.cn/TicketOrder/OrderDetail/%s?seed=0.%s"%(order.lock_info['order_id'],random.randint(10000000,100000000000))
        headers = rebot.http_header()
#         rebot.login()
#         rebot.reload()
        r = rebot.http_get(order_detail_url, headers=headers, cookies=json.loads(rebot.cookies))
        content = r.content
        if not isinstance(content, unicode):
            content = content.decode('utf-8')
        sel = etree.HTML(content)
        status = sel.xpath('//*[@id="orderItemsContainer"]/table/tbody/tr/td[12]/text()')[0]
        raw_order_list = []
        for i in range(1, order.ticket_amount+1):
            raw_order = sel.xpath('//*[@id="orderItemsContainer"]/table/tbody/tr[%s]/td[1]/text()'%i)[0]
            name = sel.xpath('//*[@id="orderItemsContainer"]/table/tbody/tr[%s]/td[6]/text()'%i)[0]
            info = name+':'+raw_order
            raw_order_list.append(info)
        return {
            "state": status,
            'raw_order_list': raw_order_list
        }

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
        rebot = BjkyWebRebot.objects.get(telephone=order.source_account)
        order_log.info("[refresh_issue_start] order: %s,account:%s start orderDetail request", order.order_no, rebot.telephone)
        ret = self.send_orderDetail_request(rebot, order=order)
        order_log.info("[refresh_issue_end] order: %s,account:%s orderDetail request result : %s", order.order_no, rebot.telephone,ret)
        state = ret["state"]
        order_status_mapping = {
                u"购票成功": "出票成功",
                u"已取消": "出票失败",
                u"已释放": "出票失败",
                u"出票中": "正在出票",
                u"出票失败": "出票失败",
                }
        if state in(u"购票成功"): #"出票成功":
            code_list = []
            msg_list = []
            dx_templ = DUAN_XIN_TEMPL[SOURCE_BJKY]
            dx_info = {
                "start": order.line.s_sta_name,
                "end": order.line.d_sta_name,
                "time": order.drv_datetime.strftime("%Y-%m-%d %H:%M"),
                "raw_order": ','.join(ret['raw_order_list']),
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
        elif state in (u"已取消", u'已释放', u"出票失败"):#取消购票,购票失败,退票成功
            result_info.update({
                "result_code": 2,
                "result_msg": order_status_mapping[state],
            })
        return result_info

    def get_pay_page(self, order, valid_code="", session=None, pay_channel="alipay" ,**kwargs):
        if order.source_account:
            rebot = BjkyWebRebot.objects.get(telephone=order.source_account)
        else:
            rebot = BjkyWebRebot.get_one(order)
        is_login = rebot.test_login_status()
        if is_login:
            if order.status in [STATUS_LOCK_RETRY, STATUS_WAITING_LOCK]:
                self.lock_ticket(order)

            if order.status == STATUS_WAITING_ISSUE:
                cookies = json.loads(rebot.cookies)
                pay_url = "http://e2go.com.cn/TicketOrder/Repay/"+order.lock_info['order_id']
                headers = rebot.http_header()
                r = rebot.http_get(pay_url, headers=headers, cookies=cookies)
                order.update(pay_channel='yh')
#                 content = r.content
#                 if isinstance(content, unicode):
#                     pass
#                 else:
#                     content = content.decode('utf-8')
#                 sel = etree.HTML(r.content)
#                 form = sel.xpath('//form[@id="pay_form"]')
#                 for sel in form:
#                     data = dict(
#                         version=sel.xpath("//input[@name='version']/@value")[0],
#                         charset=sel.xpath("//input[@name='charset']/@value")[0],
#                         merId=sel.xpath("//input[@name='merId']/@value")[0],
#                         acqCode=sel.xpath("//input[@name='acqCode']/@value")[0],
#                         merCode=sel.xpath("//input[@name='merCode']/@value")[0],
#                         merAbbr=sel.xpath("//input[@name='merAbbr']/@value")[0],
#                         transType=sel.xpath("//input[@name='transType']/@value")[0],
#                         commodityUrl=sel.xpath("//input[@name='commodityUrl']/@value")[0],
#                         commodityName=sel.xpath("//input[@name='commodityName']/@value")[0],
#                         commodityUnitPrice=sel.xpath("//input[@name='commodityUnitPrice']/@value")[0],
#                         commodityQuantity=sel.xpath("//input[@name='commodityQuantity']/@value")[0],
#                         orderNumber=sel.xpath("//input[@name='orderNumber']/@value")[0],
#                         orderAmount=sel.xpath("//input[@name='orderAmount']/@value")[0],
#                         orderCurrency=sel.xpath("//input[@name='orderCurrency']/@value")[0],
#                         orderTime=sel.xpath("//input[@name='orderTime']/@value")[0],
#                         customerIp=sel.xpath("//input[@name='customerIp']/@value")[0],
#                         frontEndUrl=sel.xpath("//input[@name='frontEndUrl']/@value")[0],
#                         backEndUrl=sel.xpath("//input[@name='backEndUrl']/@value")[0],
#                         signature=sel.xpath("//input[@name='signature']/@value")[0],
#                         origQid=sel.xpath("//input[@name='origQid']/@value")[0],
#                         commodityDiscount=sel.xpath("//input[@name='commodityDiscount']/@value")[0],
#                         transferFee=sel.xpath("//input[@name='transferFee']/@value")[0],
#                         customerName=sel.xpath("//input[@name='customerName']/@value")[0],
#                         defaultPayType=sel.xpath("//input[@name='defaultPayType']/@value")[0],
#                         defaultBankNumber=sel.xpath("//input[@name='defaultBankNumber']/@value")[0],
#                         transTimeout=sel.xpath("//input[@name='transTimeout']/@value")[0],
#                         merReserved=sel.xpath("//input[@name='merReserved']/@value")[0],
#                         signMethod=sel.xpath("//input[@name='signMethod']/@value")[0],
#                     )
#                 url = 'https://unionpaysecure.com/api/Pay.action'
#                 r = requests.post(url, data=data, headers=headers, cookies=cookies)
                return {"flag": "html", "content": r.content}
            return {"flag": "error", "content": "锁票失败"}
        if valid_code:#  登陆
            key = "pay_login_info_%s_%s" % (order.order_no, order.source_account)
            data = json.loads(session[key])
            code_url = data["valid_url"]
            headers = data["headers"]
            cookies = data["cookies"]
            data = {
                "X-Requested-With": "XMLHttpRequest",
                "backUrl": '/TicketOrder/Notic',
                "LoginName": rebot.telephone,
                "Password": rebot.password,
                "CheckCode": valid_code
            }
            url = "http://e2go.com.cn/Home/Login"
            r = rebot.http_post(url, data=data, headers=headers, cookies=cookies)
            new_cookies = r.cookies
            try:
                r = r.json()
            except:
                rebot.modify(ip='')
                return {"flag": "error", "content": ''}
            if r['ErrorCode'] == 0:
                cookies.update(dict(new_cookies))
                rebot.modify(cookies=json.dumps(cookies), is_active=True, last_login_time=dte.now(), user_agent=headers.get("User-Agent", ""))
                if order.status == STATUS_LOCK_RETRY:
                    self.lock_ticket(order)

                if order.status == STATUS_WAITING_ISSUE:
                    pay_url = "http://e2go.com.cn/TicketOrder/Repay/"+order.lock_info['order_id']
                    r = rebot.http_get(pay_url, headers={"User-Agent": rebot.user_agent}, cookies=cookies)
                    return {"flag": "html", "content": r.content}
                else:
                    return {"flag": "false", "content": order.lock_info.get('result_reason','')}
            elif r['ErrorCode'] == -2:
                data = {
                    "cookies": cookies,
                    "headers": headers,
                    "valid_url": code_url,
                }
                key = "pay_login_info_%s_%s" % (order.order_no, order.source_account)
                session[key] = json.dumps(data)
                return {"flag": "input_code", "content": ""}
            else:
                return {"flag": "false", "content": r}
        else:
            login_form_url = "http://e2go.com.cn/Home/Login?returnUrl=/TicketOrder/Notic"
            headers = {"User-Agent": rebot.user_agent or random.choice(BROWSER_USER_AGENT)}
            r = rebot.http_get(login_form_url, headers=headers)
            cookies = dict(r.cookies)
            code_url = 'http://e2go.com.cn/Home/LoginCheckCode/0.%s' % random.randint(10000000,100000000000)
            r = rebot.http_get(code_url, headers=headers, cookies=cookies)
            cookies.update(dict(r.cookies))
            data = {
                "cookies": cookies,
                "headers": headers,
                "valid_url": code_url,
            }
            key = "pay_login_info_%s_%s" % (order.order_no, order.source_account)
            session[key] = json.dumps(data)
            return {"flag": "input_code", "content": ""}

    def do_refresh_line(self, line):
        result_info = {
            "result_msg": "",
            "update_attrs": {},
        }
        rebot = None
        now = dte.now()
        update_attrs = {}
        for i in BjkyWebRebot.objects.filter(is_active=True).order_by('-last_login_time')[0:5]:
            if i.test_login_status():
                rebot = i
                break
        bjky_flag = False
        if rebot:
            bjky_flag = True
            queryline_url = "http://e2go.com.cn/TicketOrder/SearchSchedule"
            data = {
                "ArrivingStop": line.d_city_name,
                "ArrivingStopId": line.d_city_id,
                "ArrivingStopJson": line.extra_info['ArrivingStopJson'],
                "DepartureDate": line.drv_date,
                "Order": "DepartureTimeASC",
                "RideStation": line.s_sta_name,
                "RideStationId": line.s_sta_id
            }
            r = rebot.http_post(queryline_url, data=data, headers=rebot.http_header(), cookies=json.loads(rebot.cookies))
            content = r.content
            if not isinstance(content, unicode):
                content = content.decode('utf-8')
            sel = etree.HTML(content)
            scheduleList = sel.xpath('//div[@id="scheduleList"]/table/tbody/tr')
            for i in range(0, len(scheduleList), 2):
                s = scheduleList[i]
                time = s.xpath('td[@class="departureTimeCell"]/span/text()')[0]
                scheduleIdSpan = s.xpath('td[@class="scheduleAndBusLicenseCes"]/span[@class="scheduleSpan"]/span[@class="scheduleIdSpan"]/text()')[0]
                scheduleIdSpan = scheduleIdSpan.replace('\r\n', '').replace('\t',  '').replace(' ',  '')
                price = s.xpath('td[@class="ticketPriceCell"]/span[@class="ticketPriceSpan"]/span[@class="ticketPriceValueSpan"]/text()')[0]

                drv_datetime = dte.strptime("%s %s" % (line.drv_date, time), "%Y-%m-%d %H:%M")
                left_less = s.xpath('td[@class="memoCell"]/span/@class')
                left_tickets = 45
                if left_less:
                    left_tickets = 0
                line_id_args = {
                    "s_city_name": line.s_city_name,
                    "d_city_name": line.d_city_name,
                    "bus_num": scheduleIdSpan,
                    "crawl_source": line.crawl_source,
                    "drv_datetime": drv_datetime,
                }
                line_id = md5("%(s_city_name)s-%(d_city_name)s-%(drv_datetime)s-%(bus_num)s-%(crawl_source)s" % line_id_args)
                try:
                    obj = Line.objects.get(line_id=line_id)
                except Line.DoesNotExist:
                    continue
                info = {
                    "full_price": float(price),
                    "fee": 0,
                    "left_tickets": left_tickets,
                    "refresh_datetime": now,
                }
                if line_id == line.line_id:
                    update_attrs = info
                else:
                    obj.update(**info)
        if not update_attrs and not bjky_flag:
            s_sta_name = line.s_sta_name
            d_city_name = line.d_city_name
            if line.s_sta_name != u'首都机场站':
                #s_sta_name = line.s_sta_name.strip().rstrip("站")
                s_sta_name = s_sta_name+'客运站'
            ctrip_flag = True
            try:
                ctrip_line = Line.objects.get(crawl_source='ctrip',
                                              s_sta_name=s_sta_name,
                                              d_city_name=d_city_name,
                                              bus_num=line.bus_num,
                                              full_price=line.full_price,
                                              drv_date=line.drv_date,
                                              drv_time=line.drv_time,)
            except:
                ctrip_flag = False
            if ctrip_flag:
                params = dict(
                    param="/api/home",
                    method="product.getBusDetail",
                    v="1.0",
                    ref="ctrip.h5",
                    partner="ctrip.h5",
                    clientType="Android--hybrid",
                    fromCity=ctrip_line.s_city_name,
                    toCity=ctrip_line.d_city_name,
                    busNumber=ctrip_line.bus_num,
                    fromStation=ctrip_line.s_sta_name,
                    toStation=ctrip_line.d_sta_name,
                    fromDate=ctrip_line.drv_date,
                    fromTime=ctrip_line.drv_time,
                    contentType="json",
                )
                base_url = "http://m.ctrip.com/restapi/busphp/app/index.php"
                url = "%s?%s" % (base_url, urllib.urlencode(params))
                ua = random.choice(MOBILE_USER_AGENG)
                r = requests.get(url, headers={"User-Agent": ua})
                ret = r.json()
                now = dte.now()
                if ret:
                    if ret["code"] == 1:
                        info = ret["return"]
                        if info:
                            ticket_info = info["showTicketInfo"]
                            left_tickets = 0
                            if ticket_info == "有票":
                                left_tickets = 45
                            elif ticket_info.endswith("张"):
                                left_tickets = int(ticket_info[:-1])
                            elif ticket_info in ["预约购票", "无票"]:
                                left_tickets = 0
                            else:
                                pass
                            service_info = info["servicePackage"]
                            fee = 0
                            for d in service_info:
                                if d["type"] == "service":
                                    fee = d["amount"]
                                    break
                            info = {
                                "full_price": info["fullPrice"],
                                "fee": fee,
                                "left_tickets": left_tickets,
                                "refresh_datetime": now,
                            }
                            update_attrs = info
        if not update_attrs:
            result_info.update(result_msg="no line info", update_attrs={"left_tickets": 0, "refresh_datetime": now})
        else:
            result_info.update(result_msg="ok", update_attrs=update_attrs)
        return result_info
