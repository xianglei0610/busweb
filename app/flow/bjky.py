#!/usr/bin/env python
# encoding: utf-8

import requests
import json
import urllib
import re

import datetime
import random
from lxml import etree
from bs4 import BeautifulSoup
import pytesseract
import cStringIO
from PIL import Image

from app.constants import *
from app.flow.base import Flow as BaseFlow
from app.models import BjkyWebRebot, Line
from datetime import datetime as dte
from app.utils import md5
from app import order_log, line_log


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
        with BjkyWebRebot.get_and_lock(order) as rebot:
            if not rebot.test_login_status():
                lock_result.update(result_code=2,
                                   source_account=rebot.telephone,
                                   result_reason="账号未登陆")
                return lock_result
            line = order.line
            riders = order.riders
            contact_info = order.contact_info
            data = {
                    "ScheduleString":line.extra_info['ScheduleString'],
                    "StopString":line.extra_info['ArrivingStopJson']
                    }
            select_url = "http://www.e2go.com.cn/TicketOrder/SelectSchedule"
            headers = rebot.http_header()
            cookies = json.loads(rebot.cookies)
            r = requests.post(select_url, data=data, headers=headers, cookies=cookies)
            ret = r.content
            print '444444444444444444444',ret
            add_schedule_url = 'http://www.e2go.com.cn/TicketOrder/AddScheduleTicket'
            for i in riders:
                data = {
                        "AddToTicketOwnerList": False,
                        "CredentialNO": i['id_number'],
                        'CredentialType': "Identity",
                        "PassengerName": i['name'],
                        "SelectedSchedule": '',
                        "SelectedStop": '',
                        "SellInsurance": '',
                        "WithChild": '',
                        }
                r = requests.post(add_schedule_url, data=data, headers=headers, cookies=cookies)
                ret = r.content
                print ret
            order_url = 'http://www.e2go.com.cn/TicketOrder/Order'
            
#             headers.update({'Referer': 'http://www.e2go.com.cn/TicketOrder/ShoppingCart'})
#             r = requests.post(order_url, headers=headers, cookies=cookies)
#             ret = r.content
#             print '555555555555555555',ret   

            order_log.info("[lock-start] order: %s,account:%s start  lock request", order.order_no, rebot.telephone)
#             try:
#                 res = self.send_lock_request(order, rebot, data=data)
#             except Exception, e:
#                 order_log.info("[lock-end] order: %s,account:%s lock request error %s", order.order_no, rebot.telephone,e)
#                 rebot.login()
#                 rebot.reload()
#                 res = self.send_lock_request(order, rebot, data=data)
            
            order_log.info("[lock-end] order: %s,account:%s lock request result : %s", order.order_no, rebot.telephone,res)
            lock_result = {
                "lock_info": res,
                "source_account": rebot.telephone,
                "pay_money": line.real_price()*order.ticket_amount,
            }
            if res['code'] == '100':
                order_no = '333'
                expire_time = dte.now()+datetime.timedelta(seconds=60*15)
                lock_result.update({
                    "result_code": 1,
                    "result_reason": "",
                    "pay_url": "",
                    "raw_order_no": order_no,
                    "expire_datetime": expire_time,
                    "lock_info": res
                })
            else:
                errmsg = res['msg']
                for s in ["班次余票不足"]:
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

    def send_add_passenger(self, id_card, name, rebot):
        url = "http://m.daba.cn/gwapi/passenger/addPassenger.json?c=h5&sr=3966&sc=331&ver=1.5.0&env=0&st=1456998910554"
        headers = rebot.http_header()
        params = {
                "pName": name,
                "pId": id_card,
                "pType": "1"
            }
        add_url = "%s&%s" % (url, urllib.urlencode(params))
        r = requests.get(add_url, headers=headers, cookies=json.loads(rebot.cookies))
        ret = r.json()
        if ret['code'] == 0:
            cyuserid = ret['data']['cyuserid']
            if not rebot.user_id:
                rebot.modify(user_id=ret['data']['userid'])
                rebot.reload()
        elif ret['code'] == 310 and ret['msg'] == '乘客已经存在':
            query_url = "http://m.daba.cn/gwapi/passenger/queryPassengers.json?c=h5&sr=2985&sc=162&ver=1.5.0&env=0&st=1456998910554"
            r = requests.get(query_url, headers=headers, cookies=json.loads(rebot.cookies))
            ret = r.json()
            if ret['code'] == 0:
                for i in ret['data']:
                    if i['cyusercard'] == id_card:
                        cyuserid = i['cyuserid']
                        break
        return cyuserid

#     def send_lock_request(self, order, rebot, data):
#         """
#         单纯向源站发请求
#         """
#         order_url = "http://www.e2go.com.cn/TicketOrder/SelectSchedule"
#         headers = rebot.http_header()
#         r = requests.post(order_url, data=data, headers=headers, cookies=json.loads(rebot.cookies))
#         ret = r.content
#         print '444444444444444444444',ret
#         return ret

    def send_orderDetail_request(self, rebot, order=None, lock_info=None):
        order_detail_url = "http://m.daba.cn/gwapi/newOrder/orderDetail.json?c=h5&sr=3305&sc=155&ver=1.5.0&env=0&st=1457058220463"
        params = {
            "userId": rebot.user_id,
            "orderId": order.raw_order_no,
        }
        detail_url = "%s&%s" % (order_detail_url, urllib.urlencode(params))
        headers = rebot.http_header()
#         rebot.login()
#         rebot.reload()
        r = requests.get(detail_url, headers=headers, cookies=json.loads(rebot.cookies))
        ret = r.json()
        return {
            "state": ret['data']['status'],
            "order_no": ret['data']['orderid']
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
        rebot = KuaibaWapRebot.objects.get(telephone=order.source_account)
        order_log.info("[refresh_issue_start] order: %s,account:%s start orderDetail request", order.order_no, rebot.telephone)
        try:
            ret = self.send_orderDetail_request(rebot, order=order)
        except Exception, e:
            order_log.info("[refresh_issue_start] order: %s,account:%s start orderDetail request error %s", order.order_no, rebot.telephone,e)
            rebot.login()
            rebot.reload()
            ret = self.send_orderDetail_request(rebot, order=order)
        order_log.info("[refresh_issue_end] order: %s,account:%s orderDetail request result : %s", order.order_no, rebot.telephone,ret)

        if not order.raw_order_no:
            order.modify(raw_order_no=ret["order_no"])
        state = ret["state"]
        order_status_mapping = {
                "1": "等待付款",
                "2": "等待付款",
                "3": "支付成功",
                "4": "支付失败",
                "5": "已关闭",
                "6": "正在出票",
                "7": "正在出票",
                "8": "正在出票",
                "9": "正在出票",
                "10": "出票成功",
                "11": "出票失败",
                "12": "已经取票",
                }
        if state in("10", "12"): #"出票成功":
            code_list = []
            msg_list = []
            dx_templ = DUAN_XIN_TEMPL[SOURCE_KUAIBA]
            dx_info = {
                "start": order.line.s_sta_name,
                "end": order.line.d_sta_name,
                "time": order.drv_datetime.strftime("%Y-%m-%d %H:%M"),
            }
            code_list.append('无需取票密码')
            msg_list.append(dx_templ % dx_info)
            result_info.update({
                "result_code": 1,
                "result_msg": order_status_mapping[state],
                "pick_code_list": code_list,
                "pick_msg_list": msg_list,
            })
        elif state in("3", "6", "7", "8", "9"): #"出票中":
            result_info.update({
                "result_code": 4,
                "result_msg": order_status_mapping[state],
            })
        elif state in ("4", "5", "11"):#取消购票,购票失败,退票成功
            result_info.update({
                "result_code": 2,
                "result_msg": order_status_mapping[state],
            })
        return result_info

    def get_pay_page(self, order, valid_code="", session=None, pay_channel="alipay" ,**kwargs):

        if order.source_account:
            rebot = BjkyWebRebot.objects.get(telephone=order.source_account)
        else:
            rebot = BjkyWebRebot.get_one()
        if valid_code:      #  登陆
            data = json.loads(session["pay_login_info"])
            code_url = data["valid_url"]
            headers = data["headers"]
            cookies = data["cookies"]
        else:
            login_form_url = "http://www.e2go.com.cn/Home/Login?returnUrl=/TicketOrder/Notic"
            headers = {"User-Agent": rebot.user_agent or random.choice(BROWSER_USER_AGENT)}
            r = requests.get(login_form_url, headers=headers)
            cookies = dict(r.cookies)
            code_url = 'http://www.e2go.com.cn/Home/LoginCheckCode/0.2769864823920234'
            r = requests.get(code_url, headers=headers, cookies=cookies)
            cookies.update(dict(r.cookies))
            tmpIm = cStringIO.StringIO(r.content)
            im = Image.open(tmpIm)
            valid_code = pytesseract.image_to_string(im)
            if not valid_code:
                valid_code="2323"
            print '111111111111111111',valid_code
        data = {
            "X-Requested-With": "XMLHttpRequest",
            "backUrl": '/TicketOrder/Notic',
            "LoginName": rebot.telephone,
            "Password": rebot.password,
            "CheckCode": valid_code
        }
        url = "http://www.e2go.com.cn/Home/Login"
        r = requests.post(url, data=data, headers=headers, cookies=cookies)
        new_cookies = r.cookies
        print '33333333333333',r.content
        r = r.json()
        if r['ErrorCode'] == 0:
            cookies.update(dict(new_cookies))
            rebot.modify(cookies=json.dumps(cookies), is_active=True, last_login_time=dte.now(), user_agent=headers.get("User-Agent", ""))
        elif r['ErrorCode'] == -2:
            data = {
                "cookies": cookies,
                "headers": headers,
                "valid_url": code_url,
            }
            session["pay_login_info"] = json.dumps(data)
            return {"flag": "input_code", "content": ""}

    def do_refresh_line(self, line):
        result_info = {
            "result_msg": "",
            "update_attrs": {},
        }
        now = dte.now()
#         rebot = KuaibaWapRebot.get_one()
#         if not rebot.test_login_status():
#             rebot.login()
#             rebot.reload()
#         headers = rebot.http_header()
#         cookies = json.loads(rebot.cookies)

        ua = random.choice(MOBILE_USER_AGENG)
        headers = {"User-Agent": ua}
        url = "http://m.daba.cn/jsp/line/newlines.jsp"
        res = requests.get(url, headers=headers)
        base_url = 'http://m.daba.cn'
        line_url = base_url + re.findall(r'query_station : (.*),', res.content)[0][1:-1]
        params = {
              "endTime": line.extra_info['endTime'],
              "startCity": line.s_city_name,
              "startStation": line.s_sta_name,
              "arriveCity": line.d_city_name,
              "arriveStation": line.d_sta_name,
              "startDate": line.drv_date,
              "startTime": line.extra_info['startTime'],
              }

        line_url = "%s&%s" % (line_url, urllib.urlencode(params))

        r = requests.get(line_url, headers=headers)
        res = r.json()
        now = dte.now()
        if res["code"] != 0:
            result_info.update(result_msg="error response", update_attrs={"left_tickets": 0, "refresh_datetime": now})
            return result_info
        busTripInfoSet = res['data'].get('busTripInfoSet', [])
        cityOpenSale = res['data']['cityOpenSale']
        if not cityOpenSale or len(busTripInfoSet) == 0:
            result_info.update(result_msg=" not open sale or not line list", update_attrs={"left_tickets": 0, "refresh_datetime": now})
            return result_info
        update_attrs = {}
        for d in busTripInfoSet:
            drv_datetime = dte.strptime("%s %s" % (line.drv_date, d["time"][0:-3]), "%Y-%m-%d %H:%M")
            line_id_args = {
                "s_city_name": line.s_city_name,
                "d_city_name": line.d_city_name,
                "bus_num": d["id"],
                "crawl_source": line.crawl_source,
                "drv_datetime": drv_datetime,
            }
            line_id = md5("%(s_city_name)s-%(d_city_name)s-%(drv_datetime)s-%(bus_num)s-%(crawl_source)s" % line_id_args)
            try:
                obj = Line.objects.get(line_id=line_id)
            except Line.DoesNotExist:
                continue
            tickets = d['tickets']
            if d['tickets'] == 0 or d['tempClose'] == 1:
                tickets = 0
            info = {
                "full_price": float(d["price"]),
                "fee": 0,
                "left_tickets": tickets,
                "refresh_datetime": now,
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
