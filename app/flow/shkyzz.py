#!/usr/bin/env python
# encoding: utf-8

import requests
import json
import datetime
import random
from lxml import etree
from bs4 import BeautifulSoup

from app.constants import *
from app.flow.base import Flow as BaseFlow
from app.models import ShkyzzWebRebot, Line
from datetime import datetime as dte
from app.utils import md5
from tasks import async_clear_rider


class Flow(BaseFlow):

    name = "shkyzz"

    def do_lock_ticket(self, order):
        lock_result = {
            "lock_info": {},
            "source_account": '',
            "result_code": -1,
            "result_reason": "",
            "pay_url": "",
            "raw_order_no": "",
            "expire_datetime": "",
            "pay_money": "0",
        }
        rebot = order.get_lock_rebot()
        is_login = rebot.test_login_status()
        if not is_login:
            for i in range(3):
                msg = rebot.login()
                if msg == "OK":
                    is_login = True
                    break
        if not is_login:
            lock_result.update({
                "result_code": 2,
                "source_account": rebot.telephone,
                "result_reason": "账号未登录",
            })
            return lock_result
        mem_info = self.send_add_contact(order, rebot)
        cookies = self.gen_create_cookies(order, rebot)
        res = self.send_lock_request(order, rebot, mem_info, cookies)
        lock_result.update({
                    "lock_info": res,
                    "source_account": rebot.telephone,
                    "pay_money": 0,
                    })

        def _check_fail(msg):
            lst = [
                u"售票不足",
            ]
            for s in lst:
                if s in msg:
                    return True
            return False
        if res.get('order_no', ''):
            expire_time = dte.now()+datetime.timedelta(seconds=30*60)
            lock_result.update({
                "result_code": 1,
                "result_reason": "",
                "pay_url": "",
                "raw_order_no": res["order_no"],
                "expire_datetime": expire_time,
                "lock_info": res
            })
#             async_clear_rider.delay(self.name, rebot.telephone)
        elif _check_fail(res.get("msg", '')):
                self.close_line(order.line, reason=res["msg"])
                lock_result.update({
                    "result_code": 0,
                    "source_account": rebot.telephone,
                    "result_reason": res["msg"],
                })
        else:
            lock_result.update({
                "result_code": 2,
                "result_reason": res.get('msg', '') or res,
                "pay_url": "",
                "raw_order_no": "",
                "expire_datetime": None,
            })
        return lock_result

    def send_add_contact(self, order, rebot):
        contact_info = order.contact_info
        headers = {
            "Charset": "UTF-8",
            "User-Agent": rebot.user_agent,
            "Upgrade-Insecure-Requests": "1"
        }
        cookies = json.loads(rebot.cookies)
        main_url = 'http://www.zxjt.sh.cn/receiverAction!toMain'
        r = requests.get(main_url, headers=headers, cookies=cookies)
        soup = BeautifulSoup(r.content, "lxml")
        memberId = soup.find('input', attrs={'id': 'memberId'}).get('value', '')
        add_url = 'http://www.zxjt.sh.cn/ajax/receiverJsonAction!saveReceiver'
        headers = {
            "Charset": "UTF-8",
            "Content-Type": "application/x-www-form-urlencoded; charset=UTF-8",
            "User-Agent": rebot.user_agent,
            "Referer": "http://www.zxjt.sh.cn/receiverAction!toMain",
            "X-Requested-With": 'XMLHttpRequest'
        }
        data = {
                "receiverForm.address": "",
                "receiverForm.addressRing": "",
                "receiverForm.area": "",
                "receiverForm.city": "上海",
                "receiverForm.idCardNo": contact_info['id_number'],
                "receiverForm.idCardType": "身份证",
                "receiverForm.isDefault": "N",
                "receiverForm.memberId": memberId,
                "receiverForm.memberReceiverId": '',
                "receiverForm.mobilePhone": contact_info['telephone'],
                "receiverForm.receiverName": contact_info['name'],
                "receiverForm.telephone": '',
                "receiverForm.zip": '',
        }
        r = rebot.http_post(add_url, data=data, headers=headers, cookies=cookies)
        res = r.json()
        memberReceiverId = res['receiverForm']['memberReceiverId']
        return {'memberId': memberId, "memberReceiverId": memberReceiverId}

    def gen_create_cookies(self, order, rebot):
        headers = {
            'User-Agent': rebot.user_agent,
            "Upgrade-Insecure-Requests": "1",
            "Host": "www.zxjt.sh.cn",
            "Referer": "http://www.zxjt.sh.cn/flightAction.action"
        }
        url = 'http://www.zxjt.sh.cn/ticketAction!orderGen?ticketForm.flightOnlineDetailId=%s'%order.line.extra_info['raw_info']['flightOnlineDetailId']
        cookies = json.loads(rebot.cookies)
        r = rebot.http_get(url, headers=headers, cookies=cookies)
        content = r.content
        cookies.update(dict(r.cookies))
        if not isinstance(content, unicode):
            content = content.decode('utf-8')
        sel = etree.HTML(content)
        params = {}
        for s in sel.xpath("//form[@id='loginForm']/input"):
            k, v = s.xpath("@name"), s.xpath("@value")
            if not k:
                continue
            k, v = k[0], v[0] if v else ""
            params[k] = v
        login_url = "http://www.zxjt.sh.cn/memberAction.action"
        headers.update({
                        "Referer": url,
                       "Content-Type": "application/x-www-form-urlencoded; charset=UTF-8",
                       })
        r = rebot.http_post(login_url, data=params, headers=headers, cookies=cookies)
        del headers['Content-Type']
        confirm_url = 'http://www.zxjt.sh.cn/ticketAction!orderConfirm.action'
        r = rebot.http_get(confirm_url, data=params, headers=headers, cookies=cookies)
        if '网上购票协议' in r.content:
            return cookies

    def send_lock_request(self, order, rebot, mem_info, cookies):
        """
        单纯向源站发请求
        """
        headers = {
            "Charset": "UTF-8",
            "Content-Type": "application/x-www-form-urlencoded; charset=UTF-8",
            "User-Agent": rebot.user_agent,
            "Referer": "http://www.zxjt.sh.cn/ticketAction!orderConfirm.action",
            "Upgrade-Insecure-Requests": '1'
        }
        url = "http://www.zxjt.sh.cn/orderAction!orderToPay.action"
        data = {
            "ticketForm.piaoCount": order.ticket_amount,
            "ticketForm.childCount": 0,
            "ticketForm.insuranceCount": 0,
            "ticketForm.memberId": mem_info['memberId'],
            "ticketForm.expressFee": 20,
            "ticketForm.orderAmount": order.order_price,
            "ticketForm.piaoAmount": 0,
            "ticketForm.memberReceiverId": mem_info['memberReceiverId'],
            "ticketForm.parentRecId": "",
            "ticketForm.flightOnlineDetailId": order.line.extra_info['raw_info']['flightOnlineDetailId'],
            "ticketForm.insuranceAmount": 0,
            "ticketForm.insuranceType": "TARS_WEBSITE01",
            "ticketForm.insuranceList": "",
            "ticketForm.takePiaoType": "toStation"
            }
        r = rebot.http_post(url, data=data, headers=headers, cookies=cookies)
        content = r.content
        if not isinstance(content, unicode):
            content = content.decode('utf8')
        sel = etree.HTML(content)
        order_no = sel.xpath('//form[@id="orderRecForm"]//input[@name="orderRecForm.orderRecId"]/@value')
        if order_no:
            return {"order_no": order_no[0]}
        else:
            msg = sel.xpath('//div[@class="Booking_material"]/div[@class="tab_top"]/p[2]/text()')
            if msg:
                return {"msg": msg[0]}
            else:
                return {"msg": "[系统]未知错误"}

    def send_orderDetail_request(self, rebot, order=None, lock_info=None):
        detail_url = "http://www.zxjt.sh.cn/orderAction!orderDetail?orderRecForm.orderRecId=%s" % order.raw_order_no
        res = {}
        headers = {
            "Charset": "UTF-8",
            "User-Agent": rebot.user_agent,
            "Referer": "http://www.zxjt.sh.cn/orderAction!myOrder",
            "Upgrade-Insecure-Requests": '1'
        }
        cookies = json.loads(rebot.cookies)
        r = rebot.http_get(detail_url, headers=headers, cookies=cookies)
        content = r.content
        soup = BeautifulSoup(content, "lxml")
        state = soup.find('div', attrs={'class': 'hyzx_right'}).find('table').find_all('tr')[0].find_all('td')[1].get_text()
        order_status = state.encode("utf-8").split('：')[1]
        res.update({"order_status": order_status,})
        if order_status not in ['待领票', "已领票","购票暂时失败且未退款"]:
            return res
        else:
            photo_url = "http://www.kyzz.com.cn/orderAction!toSelfPhoto?orderRecForm.orderRecId=%s" % order.raw_order_no
            cookies = json.loads(rebot.cookies)
            r = rebot.http_get(photo_url, headers=headers, cookies=cookies)
            content = r.content
            soup = BeautifulSoup(content, "lxml")
            pcode = soup.find('div', attrs={'id': 'printDiv'}).find('p').get_text()
            pcode = pcode.encode("utf-8").split('：')[1]
            check_no = soup.find('div', attrs={'id': 'printDiv'}).find('table').find_all('tr')[2].find_all('td')[1].get_text()
            check_no = check_no.encode("utf-8").split('：')[1]
            address = soup.find('div', attrs={'id': 'printDiv'}).find('table').find_all('tr')[3].find_all('td')[1].get_text()
            address = address.encode("utf-8").split('：')[1]
            seat_no = soup.find('div', attrs={'id': 'printDiv'}).find('table').find_all('tr')[4].find_all('td')[0].get_text()
            seat_no = seat_no.encode("utf-8").split('：')[1]
            res.update({"pcode": pcode,
                        'check_no': check_no,
                        'address': address,
                        "seat_no": seat_no})
            return res

    def do_refresh_issue(self, order):
        result_info = {
            "result_code": 0,
            "result_msg": "",
            "pick_code_list": [],
            "pick_msg_list": [],
        }
        rebot = ShkyzzWebRebot.objects.get(telephone=order.source_account)
        ret = self.send_orderDetail_request(rebot, order=order)
        state = ret["order_status"]
        order_status_mapping = {
                "订单过期": u"订单过期",
                "待领票": u"购票成功",
                "已领票": u"购票成功",
                "正在出票":u'正在出票',
                "已支付":u"已支付，暂时未出票",
                "购票暂时失败且未退款":'购票暂时失败且未退款'
                }
        if state in ["待领票", "已领票"]: #"出票成功":
            dx_info = {
                "time": order.drv_datetime.strftime("%Y-%m-%d %H:%M"),
                "start": order.line.s_sta_name,
                "end": order.line.d_sta_name,
                "seat_no": ret['seat_no'],
                "check_no": ret['check_no'],
                'code': ret['pcode'],
                "address": ret['address']
            }
            code_list = []
            code_list.append(ret['pcode'])
            dx_tmpl = DUAN_XIN_TEMPL[order.line.s_sta_name]
            msg_list = [dx_tmpl % dx_info]
            result_info.update({
                "result_code": 1,
                "result_msg": order_status_mapping[state],
                "pick_code_list": code_list,
                "pick_msg_list": msg_list,
            })
        elif state in ["正在出票","已支付"]:
            result_info.update({
                "result_code": 4,
                "result_msg": order_status_mapping[state],
            })
        elif state in ["购票暂时失败且未退款"]:
            result_info.update({
                "result_code": 2,
                "result_msg": order_status_mapping[state],
            })
        return result_info

    def get_pay_page(self, order, valid_code="", session=None, pay_channel="alipay" ,**kwargs):
        rebot = order.get_lock_rebot()
        is_login = rebot.test_login_status()
        if not is_login:
            for i in range(3):
                msg = rebot.login()
                if msg == "OK":
                    break

        def _get_page(rebot):
            if order.status == STATUS_WAITING_ISSUE:
                ret = self.send_orderDetail_request(rebot, order=order)
                order_status = ret["order_status"]
                if order_status in ('支付中','未支付'):
                    headers = {
                           'User-Agent': rebot.user_agent,
                           "Host": "www.zxjt.sh.cn",
                           "Referer": "http://www.zxjt.sh.cn/orderAction!myOrder",
                           "Upgrade-Insecure-Requests": "1",
                        }
                    order_url = "http://www.zxjt.sh.cn/orderAction!orderToPayById?orderRecForm.orderRecId=%s"%order.raw_order_no
                    cookies = json.loads(rebot.cookies)
                    r = rebot.http_get(order_url, headers=headers, cookies=cookies)
                    res = r.content
                    if not isinstance(res, unicode):
                        res = res.decode('utf8')
                    sel = etree.HTML(res)
                    params = {}
                    for s in sel.xpath("//form//input"):
                        k, v = s.xpath("@name"), s.xpath("@value")
                        if not k:
                            continue
                        k, v = k[0], v[0] if v else ""
                        params[k] = v
                    if not params:
                        msg = sel.xpath('//div[@class="Booking_material"]/div[@class="tab_top"]/p[2]/text()')
                        if msg:
                            order.modify(status=STATUS_LOCK_RETRY)
                            order.on_lock_retry(reason=msg[0])
                            return {"flag": "error", "content": '支付错误'}
                    pay_money = params['orderRecForm.orderAmount']
                    order.modify(pay_money=float(pay_money), pay_channel='alipay')
                    headers.update({"Referer": order_url})
                    pay_url = 'http://www.zxjt.sh.cn/orderAction.action'
                    r = rebot.http_post(pay_url, data=params, headers=headers, cookies=cookies)
                    return {"flag": "html", "content": r.content}
            return {"flag": "error", "content": "订单已支付成功或者失效"}
        if order.status in (STATUS_WAITING_LOCK, STATUS_LOCK_RETRY):
            self.lock_ticket(order)
        return _get_page(rebot)

    def do_refresh_line(self, line):
        result_info = {
            "result_msg": "",
            "update_attrs": {},
        }
        now = dte.now()
        rebot = ShkyzzWebRebot.get_one()
        headers = {
            'User-Agent': random.choice(BROWSER_USER_AGENT),
            "Upgrade-Insecure-Requests": "1",
            "Host": "www.zxjt.sh.cn",
            "Content-Type": "application/x-www-form-urlencoded; charset=UTF-8",
        }
        data = {
                  "searchForm.fromRegionName": line.s_city_name,
                  "searchForm.arriveRegionName": line.d_city_name,
                  "searchForm.flightDate": line.drv_date,
                  "__multiselect_searchForm.stationIdArr": '',
                  "searchForm.startDate": '',
                  "searchForm.selFlightCountFlag": "true",
                }
        url = "http://www.zxjt.sh.cn/ajax/flightJsonAction!search"
        try:
            r = rebot.http_post(url, data=data, headers=headers)
            res = r.json()
        except:
            result_info.update(result_msg="timeout default 10", update_attrs={"left_tickets": 10, "refresh_datetime": now})
            return result_info
        update_attrs = {}
        for d in res.get('flightList', []):
            drv_datetime = dte.strptime("%s %s" % (line.drv_date, d['flightTime']), "%Y-%m-%d %H:%M")
            line_id_args = {
                "s_city_name": line.s_city_name,
                "d_city_name": d['arriveRegionName'],
                "bus_num": d['flightNo'],
                "crawl_source": line.crawl_source,
                "drv_datetime": drv_datetime,
            }
            line_id = md5("%(s_city_name)s-%(d_city_name)s-%(drv_datetime)s-%(bus_num)s-%(crawl_source)s" % line_id_args)
            try:
                obj = Line.objects.get(line_id=line_id)
            except Line.DoesNotExist:
                continue
            info = {
                "full_price": float(d['price']),
                "fee": 0,
                "left_tickets": int(d['lastCount']),
                "refresh_datetime": now,
                "extra_info": {"raw_info": d},
            }
            if line_id == line.line_id:
                update_attrs = info
            else:
                obj.update(**info)
        if not update_attrs:
            result_info.update(result_msg="no line info", update_attrs={"left_tickets": 0, "refresh_datetime": now})
        else:
            result_info.update(result_msg="ok", update_attrs=update_attrs)
        return result_info
