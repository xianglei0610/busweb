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

from app.constants import *
from app.flow.base import Flow as BaseFlow
from app.models import KuaibaWapRebot, Line
from datetime import datetime as dte
from app.utils import md5
from app import order_log, line_log


class Flow(BaseFlow):

    name = "kuaiba"

    def do_lock_ticket(self, order):
        with KuaibaWapRebot.get_and_lock(order) as rebot:
            if not rebot.test_login_status():
                rebot.login()
                rebot.reload()
            line = order.line
            riders = order.riders
            contact_info = order.contact_info
            passengers = []
            buyPersonCard = riders[0]['id_number']
            buyPersonName = riders[0]['name']
            buyPersonPhone = contact_info['telephone']
            for r in riders:
                cyuserid = self.send_add_passenger(r["id_number"], r["name"], rebot)
                passengers.append(cyuserid)
                if r["id_number"] == contact_info['id_number'] and r["name"] == contact_info['name']: #如果联系人中没有乘车人就取第一个乘车人作为取票人
                    buyPersonName = contact_info['name']
                    buyPersonCard = contact_info['id_number']
            data = {
                "userId": rebot.user_id,
                "buyPersonName": buyPersonName,
                "insuCode": "",
                "buyPersonCard": buyPersonCard,
                "insuType": '',
                "buyPersonPhone": buyPersonPhone,
                "couponId": '',
                "insuPrice": '0',
                'token': '',
                "lineBcId": order.line.shift_id,
                "passengers": ','.join(passengers),
                }

            order_log.info("[lock-start] order: %s,account:%s start  lock request", order.order_no, rebot.telephone)
            try:
                res = self.send_lock_request(order, rebot, data=data)
            except Exception, e:
                order_log.info("[lock-end] order: %s,account:%s lock request error %s", order.order_no, rebot.telephone,e)
                rebot.login()
                rebot.reload()
                res = self.send_lock_request(order, rebot, data=data)
            order_log.info("[lock-end] order: %s,account:%s lock request result : %s", order.order_no, rebot.telephone,res)
            lock_result = {
                "lock_info": res,
                "source_account": rebot.telephone,
                "pay_money": line.real_price()*order.ticket_amount,
            }
            if res['code'] == '100':
                order_no = res["data"]['orderid']
                closetime = int(res["data"]['closetime'])
                expire_time = dte.now()+datetime.timedelta(seconds=60*closetime)
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

    def send_lock_request(self, order, rebot, data):
        """
        单纯向源站发请求
        """
        order_url = "http://m.daba.cn/gwapi/newOrder/addOrderEx.json?c=h5&sr=3196&sc=747&ver=1.5.0&env=0&st=1457000660239"
        headers = rebot.http_header()
        order_url = "%s&%s" % (order_url, urllib.urlencode(data))
        r = requests.get(order_url, data=data, headers=headers, cookies=json.loads(rebot.cookies))
        ret = r.json()
        return ret

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
        rebot = KuaibaWapRebot.objects.get(telephone=order.source_account)

        def _get_page(rebot):
            if order.status == STATUS_WAITING_ISSUE:
                headers = rebot.http_header()
                callback_url = "http://m.daba.cn/jsp/order/orderdetail.jsp?c=h5&sr=7327&sc=483&ver=1.5.0&env=0&st=1456912139874&orderid=%s"%order.raw_order_no
        #         rebot.login()
        #         rebot.reload()
#                 r = requests.get(callback_url, headers=headers, cookies=json.loads(rebot.cookies))
                pay_url = "http://m.daba.cn/gwapi/newOrder/pay.json?c=h5&sr=6636&sc=161&ver=1.5.0&env=0&st=1457076498612env=0&c=h5&ver=1.5.0"
                params = {
                        "orderId": order.raw_order_no,
                        "payMethod": '2',
                        "opsrc": "",
                        "token": "",
                        "callBackUrl": callback_url,
                        "openId": "",
                    }
                pay_url = "%s&%s" % (pay_url, urllib.urlencode(params))
                cookies = json.loads(rebot.cookies)
                r = requests.get(pay_url, headers=headers, cookies=cookies)
                cookies.update(dict(r.cookies))
                res = r.json()
                if res['flag'] == False:
                    return res
                data = r.json()['data']
                sel = etree.HTML(data)
                pay_order_no = sel.xpath("//input[@name='out_trade_no']/@value")[0].strip()
                if order.pay_order_no != pay_order_no:
                    order.update(pay_order_no=pay_order_no)
                return {"flag": "html", "content": data}

        is_login = rebot.test_login_status()

        if not is_login:
            rebot.login()
            rebot.reload()
        if order.status == STATUS_LOCK_RETRY:
            self.lock_ticket(order)
        return _get_page(rebot)

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
        print '333333333333333333333333333',res
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
                "bus_num": '',
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
