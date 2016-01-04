# -*- coding:utf-8 -*-
import random
import urllib2
import requests
import datetime
import json

from lxml import etree
from app.constants import *
from app.flow.base import Flow as BaseFlow
from app.models import Bus100Rebot, Line
from datetime import datetime as dte

class Flow(BaseFlow):
    name = "bus100"

    def do_lock_ticket(self, order):
        rebot = Bus100Rebot.get_random_rebot()
        ret = rebot.recrawl_shiftid(order.line)
        line = Line.objects.get(line_id=order.line.line_id)
        order.line = line
        order.ticket_price = line.full_price
        order.save()

        lock_result = {
            "lock_info": {},
            "source_account": rebot.telephone,
            "result_code": 0,
            "result_reason": "",
            "pay_url": "",
            "raw_order_no": "",
            "expire_datetime": "",
            "pay_money": 0,
        }

        if order.line.bus_num == 0 or not order.line.extra_info.get('flag', 0):
            lock_result.update(result_reason="该条线路无法购买")
            return lock_result

        url = 'http://wap.84100.com/wap/login/ajaxLogin.do'
        data = {
              "mobile": rebot.telephone,
              "password": rebot.password,
              "phone":   '',
              "code":  ''
        }
        ua = random.choice(MOBILE_USER_AGENG)
        headers = {"User-Agent": ua}
        r = requests.post(url, data=data, headers=headers)
        rebot.cookies = r.cookies

        passengerList = []
        for r in order.riders:
            tmp = {}
            tmp['idType'] = r["id_type"]
            tmp['idNo'] = r["id_number"]
            tmp['name'] = r["name"]
            tmp['mobile'] = r["telephone"]
            tmp['ticketType'] = "全票"
            passengerList.append(tmp)

        data = {
            "startId": order.line.starting.station_id,
            "planId": order.line.bus_num,
            "name": order.contact_info['name'],
            "mobile": order.contact_info['telephone'],
            "password": '',
            "terminalType": 3,
            "passengerList": json.dumps(passengerList),
            "openId": rebot.open_id or 1,
            "isWeixin": 1,
        }
        ret = self.request_lock(rebot, data)
        pay_url = ret.get('redirectPage', '')
        returnMsg = ret.get('returnMsg', '')

        if ret["returnCode"] == "0000" and ret.get('redirectPage', ''):
            pay_info = self.request_pay_info(pay_url)
            lock_result.update({
                "result_code": 1,
                "lock_info": ret,
                "pay_url": pay_url,
                "raw_order_no": pay_info["order_no"],
                "expire_datetime": dte.now()+datetime.timedelta(seconds=20*60),
                "pay_money": pay_info["pay_money"]
            })
        else:
            lock_result.update({
                "lock_info": ret,
            })
        return lock_result

    def request_lock(self, rebot, data):
        url = urllib2.urlparse.urljoin(Bus100_DOMAIN, "/wap/ticketSales/ajaxMakeOrder.do")
        ret = requests.post(url, data=data, cookies=rebot.cookies)
        return ret.json()

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
        if order.status != STATUS_WAITING_ISSUE:
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
        return result_info

    def send_order_request(self, order, rebot):
        data = {"orderId": order.raw_order_no}
        url = "http://www.84100.com/orderInfo.shtml"
        r = requests.post(url, data=data)
        sel = etree.HTML(r.content)
        orderDetailObj = sel.xpath('//div[@class="order-details"]/ul')
        orderDetail = {}
        if orderDetailObj:
            status = orderDetailObj[0].xpath('li')[1].xpath('em/text()')[0].replace('\r\n','').replace(' ','')
            if not status:
                orderDetail.update({'status': '5'})
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
        rebot = Bus100Rebot.objects.first()
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
            trainInfo = requests.post(url, data=payload)
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

    def get_pay_page(self, order, **kwargs):
        pay_url = order.pay_url
        headers = {
            'User-Agent': "Mozilla/5.0 (Windows NT 6.1; WOW64; rv:42.0) Gecko/20100101 Firefox/42.0",
        }
        r = requests.get(pay_url, headers=headers, verify=False)
        cookies = dict(r.cookies)

        sel = etree.HTML(r.content)
        try:
            data = dict(
                orderId=sel.xpath('//form[@id="alipayForm"]/input[@id="alipayOrderId"]/@value')[0],
                orderAmt=sel.xpath('//form[@id="alipayForm"]/input[@id="alipayOrderAmt"]/@value')[0],
            )
        except:
            return redirect(pay_url)
        check_url = 'https://pay.84100.com/payment/alipay/orderCheck.do'

        r = requests.post(check_url, data=data, headers=headers, cookies=cookies, verify=False)
        checkInfo = r.json()
        orderNo = checkInfo['request_so']
        data = dict(
            orderId=sel.xpath('//form[@id="alipayForm"]/input[@id="alipayOrderId"]/@value')[0],
            orderAmt=sel.xpath('//form[@id="alipayForm"]/input[@id="alipayOrderAmt"]/@value')[0],
            orderNo=orderNo,
            orderInfo=sel.xpath('//form[@id="alipayForm"]/input[@name="orderInfo"]/@value')[0],
            count=sel.xpath('//form[@id="alipayForm"]/input[@name="count"]/@value')[0],
            isMobile=sel.xpath('//form[@id="alipayForm"]/input[@name="isMobile"]/@value')[0],
        )

        info_url = "https://pay.84100.com/payment/page/alipayapi.jsp"
        r = requests.post(info_url, data=data, headers=headers, cookies=cookies, verify=False)
        return {"flag": "html", "content": r.content}
