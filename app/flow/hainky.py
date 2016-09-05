#!/usr/bin/env python
# encoding: utf-8

import requests
import json
import urllib
import urlparse

import datetime
import random
import time
from lxml import etree
import re
from bs4 import BeautifulSoup

try:
    import xml.etree.cElementTree as ET
except ImportError:
    import xml.etree.ElementTree as ET

from app.constants import *
from app.flow.base import Flow as BaseFlow
from app.models import HainkyWebRebot, Line
from datetime import datetime as dte
from app.utils import md5
from app import order_log, line_log


class Flow(BaseFlow):

    name = "hainky"

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
        line = order.line
        res = self.query_request_cxbh(line, rebot)
        if res['status'] == '1':
            lock_result.update(result_code=2,
                               source_account=rebot.telephone,
                               result_reason="未查询到cxbh")
            return lock_result
        res = self.send_lock_request(order, rebot, res)
        lock_result.update({
            "lock_info": res,
            "source_account": rebot.telephone,
            "pay_money": 0,
        })
        if res.get('status', []):
            order_no = res["order_no"]
            expire_time = dte.now()+datetime.timedelta(seconds=20*60)
            lock_result.update({
                "result_code": 1,
                "result_reason": "",
                "pay_url": "",
                "raw_order_no": order_no,
                "expire_datetime": expire_time,
                "lock_info": res
            })
        else:
            errmsg = res.get('msg', '')
            if "联系人姓名转换错误" in errmsg:
                lock_result.update({
                    "result_code": 2,
                    "source_account": rebot.telephone,
                    "result_reason": errmsg,
                })
                return lock_result
            lock_result.update({
                "result_code": 0,
                "result_reason": res.get('msg', '') or res,
                "pay_url": "",
                "raw_order_no": "",
                "expire_datetime": None,
            })
        return lock_result

    def query_request_cxbh(self, line, rebot):
        headers = {'User-Agent': random.choice(BROWSER_USER_AGENT)}
        url = "http://www.0898hq.com/eTicket/QueryRegu.aspx"
        params = {
            "czbh": line.s_sta_id,
            "mdzh": line.d_city_id,
            "fcrq": line.drv_date,
            "fcsj": '00:00-23:59',
            "buyNum": '1'
        }
        url = "%s?%s" % (url, urllib.urlencode(params))
        r = requests.get(url, headers=headers)
        sel = etree.HTML(r.content.decode('gbk'))
        res = {}
        try:
            href = sel.xpath('//a[@target="_self"]/@href')[0]
            cxbh = re.findall(r'cxbh=(.*)&', href)[0]
            res.update({"status": 0, "cxbh": cxbh})
        except:
            res.update({"status": 1})
        return res

    def send_lock_request(self, order, rebot, res):
        """
        单纯向源站发请求
        """
        headers = {'User-Agent': random.choice(BROWSER_USER_AGENT)}
        line = order.line
        url = "http://www.0898hq.com/eTicket/ConfirmOrder.aspx"
        params = {
                "czbh": line.s_sta_id,
                "ccbh": line.bus_num,
                "mdzh": line.d_city_id,
                "cxbh": res['cxbh'],
                "fcrq": line.drv_date,
                "buynum": order.ticket_amount,
                }
        check_url = "%s?%s" % (url, urllib.urlencode(params))
        r = rebot.http_get(check_url, headers=headers)
        sel = etree.HTML(r.content.decode('gbk'))
        init_data = {}
        for s in sel.xpath("//form[@id='frmConfirmOrder']//input"):
            k, v = s.xpath("@name"), s.xpath("@value")
            if not k:
                continue
            k, v = k[0], v[0] if v else ""
            init_data[k] = v
        tpass = str(random.randint(111111, 999999))
        try:
            order.contact_info['name'].encode('gb2312')
        except:
            errorMsg = '联系人姓名转换错误'
            res = {"status": 0, 'msg': errorMsg}
            return res
        data = {
            "UserName": order.contact_info['name'].encode('gb2312'), 
            'IDCardType': u'身份证'.encode('gb2312'),  
            "IDCardNo": order.contact_info['id_number'],
            "TPwd": tpass,
            "TPwdConfirm": tpass,
            "MobileNo": order.contact_info['telephone'],
        }
        init_data.update(data)
        r = rebot.http_post(url, data=init_data, headers=headers, allow_redirects=False)
        location_url = r.headers.get('location', '')
        res = {}
        if location_url:
            result = urlparse.urlparse(location_url)
            params = urlparse.parse_qs(result.query, True)
            oid = params.get('oid', [])
            errorMsg = params.get('errorMsg', [])
            if oid:
                pay_url = "http://www.0898hq.com"+location_url
                r = rebot.http_get(pay_url, headers=headers)
                sel = etree.HTML(r.content)
                order_no = sel.xpath('//input[@id="OrderNo"]/@value')[0]
                order.modify(extra_info={'pcode': tpass})
                res = {"status": 1, "pay_url": pay_url, 'pay_order_id': oid[0],"order_no":order_no}
            elif errorMsg:
                res = {"status": 0, 'msg': errorMsg}
        return res

    def send_orderDetail_request(self, rebot, order=None, lock_info=None):
        detail_url = "http://www.0898hq.com/eTicket/OrderDetail.aspx?oid=%s&sid=%s"%(order.raw_order_no,order.contact_info['id_number'])
        headers = {'User-Agent': random.choice(BROWSER_USER_AGENT)}
        r = rebot.http_get(detail_url, headers=headers)
        ret = r.content.decode('gbk', "ignore")
        if u'错误订单号，订单不存在' in ret:
            state = '订单过期'
            return {"order_status": state}
        soup = BeautifulSoup(ret, "lxml")
        state = soup.find('table', attrs={'class': 'tb_style1'}).find('tbody').find('tr').find_all('td')[4].get_text()
        return {
            "order_status": state,
        }

    def do_refresh_issue(self, order):
        result_info = {
            "result_code": 0,
            "result_msg": "",
            "pick_code_list": [],
            "pick_msg_list": [],
        }
        rebot = HainkyWebRebot.objects.get(telephone=order.source_account)
        ret = self.send_orderDetail_request(rebot, order=order)
        state = ret["order_status"]
        pcode = order.extra_info.get("pcode", '')
        order_status_mapping = {
                "订单过期": "订单过期",
                "已购票": "购票成功",
                }

        if state in ["已购票"]: #"出票成功":
            dx_info = {
                "time": order.drv_datetime.strftime("%Y-%m-%d %H:%M"),
                "start": "%s(%s)" % (order.line.s_city_name, order.line.s_sta_name),
                "end": order.line.d_sta_name,
                'raw_order': order.raw_order_no,
                "code": pcode
            }
            code_list = []
            if pcode:
                code_list.append(str(pcode))
            else:
                code_list.append('无需取票密码')
            dx_tmpl = DUAN_XIN_TEMPL[SOURCE_HAINKY]
            msg_list = [dx_tmpl % dx_info]
            result_info.update({
                "result_code": 1,
                "result_msg": state,
                "pick_code_list": code_list,
                "pick_msg_list": msg_list,
            })
#         elif state in ["订单过期"]:
#             result_info.update({
#                 "result_code": 2,
#                 "result_msg": order_status_mapping[state],
#             })
        return result_info

    def get_pay_page(self, order, valid_code="", session=None, pay_channel="alipay" ,**kwargs):
        rebot = order.get_lock_rebot()
        def _get_page(rebot):
            if order.status == STATUS_WAITING_ISSUE:
                headers = {'User-Agent': random.choice(BROWSER_USER_AGENT)}
                ret = self.send_orderDetail_request(rebot, order=order)
                order_status = ret["order_status"]
                if order_status in ('未支付',):
                    union_url = "http://www.0898hq.com/eTicket/Pay2ChinaUnion.aspx?oid=%s" % order.lock_info['pay_order_id']
                    r = rebot.http_get(union_url, headers=headers)
                    res = r.content.decode('gbk', 'ignore')
                    if u'错误订单号，订单不存在' in res:
                        errmsg = u'错误订单号，订单不存在'
                        order.modify(status=STATUS_LOCK_RETRY)
                        order.on_lock_retry(reason=errmsg)
                        return {"flag": "error", "content": '重新打开'}
                    sel = etree.HTML(res)
                    params = {}
                    for s in sel.xpath("//form//input"):
                        k, v = s.xpath("@name"), s.xpath("@value")
                        if not k:
                            continue
                        k, v = k[0], v[0] if v else ""
                        params[k] = v
                    pay_money = float(params['TransAmt'])/100.0
                    order.update(pay_money=pay_money, pay_channel='yh')
                    return {"flag": "url", "content": union_url}
                elif order_status in ('订单过期',):
                    errmsg = u'订单过期'
                    order.modify(status=STATUS_LOCK_RETRY)
                    order.on_lock_retry(reason=errmsg)
                    return {"flag": "error", "content": '重新打开'}
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
        rebot = HainkyWebRebot.get_one()
        headers = rebot.http_header()
        data = {
            "ddzm": line.d_city_name,
            "fcrq": line.drv_date,
            "fcsj_e": "24:00",
            "fcsj_b": "00:00",
            "czbh": line.s_sta_id
        }
        url = "http://www.0898hq.com:8088/HaiQiServer//queryScheduledAction!queryScheduled.action"
        try:
            r = rebot.http_post(url, data=data, headers=headers)
            xml_msg = r.json().get('msg', '')
            xml_real = re.findall(r"<getScheduledBusResult>(.*)</getScheduledBusResult>",xml_msg,re.S)[0]
            root = ET.fromstring(xml_real)
            node_find = root.find('Body')
            res = node_find.findall('ScheduledBus')
        except:
            result_info.update(result_msg="timeout default 10", update_attrs={"left_tickets": 10, "refresh_datetime": now})
            return result_info
        update_attrs = {}
        if node_find.attrib['size'] != '0':
            for d in res:
                drv_time = d.find('FCSJ').text
                drv_date = d.find('FCRQ').text
                bus_num = d.find('CCBH').text
                full_price = d.find('PJ').text
                left_tickets = d.find('YPZS').text
                drv_datetime = dte.strptime("%s %s" % (drv_date, drv_time), "%Y-%m-%d %H:%M")
                line_id_args = {
                    "s_city_name": line.s_city_name,
                    "d_city_name": line.d_city_name,
                    "bus_num": bus_num,
                    "crawl_source": line.crawl_source,
                    "drv_datetime": drv_datetime,
                }
                line_id = md5("%(s_city_name)s-%(d_city_name)s-%(drv_datetime)s-%(bus_num)s-%(crawl_source)s" % line_id_args)
                try:
                    obj = Line.objects.get(line_id=line_id)
                except Line.DoesNotExist:
                    continue
                info = {
                    "full_price": float(full_price),
                    "fee": 0,
                    "left_tickets": int(left_tickets),
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
