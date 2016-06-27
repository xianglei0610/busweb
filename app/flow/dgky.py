#!/usr/bin/env python
# encoding: utf8
import time
import json
import requests
import urllib
import random
import datetime
import urllib2
import cookielib
import re
from lxml import etree

from app.constants import *
from app import config
from app.flow.base import Flow as BaseFlow
from app.utils import md5
from datetime import datetime as dte
from app.models import Line


class Flow(BaseFlow):

    name = "dgky"

    def do_lock_ticket(self, order):
        lock_result = {
            "lock_info": {},
            "source_account": "",
            "result_code": 0,
            "result_reason": "",
            "pay_url": "",
            "raw_order_no": "",
            "expire_datetime": "",
            "pay_money": 0,
        }
        ua = random.choice(BROWSER_USER_AGENT)
        headers = {
               "User-Agent": ua,
               "Referer": "http://www.mp0769.com/",
               "Host": "www.mp0769.com",
               }
        cj = cookielib.LWPCookieJar()
        cookie_support = urllib2.HTTPCookieProcessor(cj)
        opener = urllib2.build_opener(cookie_support, urllib2.HTTPHandler)
        urllib2.install_opener(opener)
        url = "http://www.mp0769.com/checkcode.asp?t="
        url = url+str(int(time.time()))
        req = urllib2.Request(url, headers=headers)
        result = urllib2.urlopen(req)
        code = ''
        line = order.line
        num = len(order.riders)
        
        query_url = line.extra_info['query_url']
        query_url = query_url.replace('num=1', 'num=%s' % num)
        for i in range(50):
            req = urllib2.Request(query_url, headers=headers)
            result = urllib2.urlopen(req)
            content = result.read()
            res = content
            check_url = re.findall("window.location.href=(.*);", res)[0][1:-1]
            check_url = "http://www.mp0769.com/" + check_url
            param = {}
            for s in check_url.split("?")[1].split("&"):
                k, v = s.split("=")
                param[k] = v
            print param
            trade_no = param['trade_no']
            Depot = param['Depot']
            order_url = "http://www.mp0769.com/orderlist.asp?"
            order_url = "%s%s" % (order_url, urllib.urlencode(param))
            req = urllib2.Request(order_url, headers=headers)
            result = urllib2.urlopen(req)
            content = result.read()
            sel = etree.HTML(content)
            params = {}
            for s in sel.xpath("//form[@id='Form1']//input"):
                k, v = s.xpath("@name"), s.xpath("@value")
                if k:
                    k, v = k[0], v[0] if k else ""
                    params[k] = v.encode('gb2312')
            
            if not params or int(params['ct_price']) == 0:
                continue
            else:
                print "ct_price ", params['ct_price']
                ct_price = params['ct_price']
                full_price = params['ct_price']
                left_tickets = params['ct_accnum']
                end_station = params['ct_stname'].decode('gbk')
                break
        if float(full_price) > 0:
            agree_url = sel.xpath('//form[@id="Form1"]/@action')[0]
            agree_url = "http://www.mp0769.com/" + agree_url
            print params
            print agree_url
            data = urllib.urlencode(params) 
            req = urllib2.Request(agree_url, data, headers=headers)
            result = urllib2.urlopen(req)
            content = result.read()
            
            sel = etree.HTML(content)
            params = {}
            for s in sel.xpath("//form[@name='register']//input"):
                k, v = s.xpath("@name"), s.xpath("@value")
                if k:
                    k, v = k[0], v[0] if k else ""
                    params[k] = v.encode('gb2312')
            params = params
            print params
            save_url = sel.xpath("//form[@name='register']/@action")[0]
            save_url = "http://www.mp0769.com/" + save_url
            print params
            print save_url
            data = urllib.urlencode(params) 
            req = urllib2.Request(save_url, data,headers=headers)
            result = urllib2.urlopen(req)
            content = result.read()
            sel = etree.HTML(content)
            params = {}
            T_Amt = sel.xpath("//input[@id='T_Amt']/@value")[0]      #票款
            T_Pnum = sel.xpath("//input[@id='T_Pnum']/@value")[0]    #购买张数
            T_Price = sel.xpath("//input[@id='T_Price']/@value")[0]  #票价 
            T_Qamt = sel.xpath("//input[@id='T_Qamt']/@value")[0]    #服务费
            T_Zamt = sel.xpath("//input[@id='T_Zamt']/@value")[0]    #总金额

            params = {
                    "T_Address": "",
                    "T_Amt": T_Amt,
                    "T_Email": "",
                    "T_Mobile": order.contact_info["telephone"],
                    "T_Password": '654322',
                    "T_Password1": '654322',
                    "T_Pnum": T_Pnum,
                    "T_Price": T_Price,
                    "T_Qamt": T_Qamt,
                    "T_TrueName": order.contact_info["name"].decode('utf8').encode('gb2312'),
                    "T_Usercard": "429006199012280042",#order.contact_info["id_number"],
                    "T_Usercard1": "429006199012280042",#order.contact_info["id_number"],
                    "T_Zamt": T_Zamt,
                    "T_Zjname": '1',  #取票凭证 身份证 1
                    "submit":  u'提交[在线支付票款]'.encode('gb2312')
                    }
            
            send_url = sel.xpath("//form[@name='form8']/@action")[0]      #url
            send_url = "http://www.mp0769.com/"+send_url
            print send_url
            data = urllib.urlencode(params) 
            req = urllib2.Request(send_url, data, headers=headers)
            result = urllib2.urlopen(req)
            content = result.read()
            print content.decode('gbk')
            pay_url = re.findall('window.open \((.*),', content)[0][1:-1]
            pay_url = "http://www.mp0769.com/" + pay_url
            print pay_url
        msg = ''
        if pay_url:
            expire_time = dte.now()+datetime.timedelta(seconds=15*60)
            lock_result.update({
                "result_code": 1,
                "result_reason": '',
                "pay_url": pay_url,
                "raw_order_no": trade_no,
                "expire_datetime": expire_time,
                "lock_info": {},
                "pay_money": T_Zamt
            })
        else:
            lock_result.update({
                "result_code": 0,
                "result_reason": msg,
                "pay_url": "",
                "raw_order_no": "",
                "expire_datetime": None,
                "lock_info": {},
            })
        return lock_result

    def request_order_detail(self, order):
        """
        3：锁票成功
        14：出票成功
        13：出票失败
        2：正在出票
        """
        fd = self.post_data_templ("U0202", order.order_no)
        r = requests.post(url, headers=self.post_headers(), data=urllib.urlencode(fd))
        ret = r.json()
        return ret

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

        ret = self.request_order_detail(order)
        if ret["code"] != 2103:
            return
        detail = ret["data"]
        state = detail["status"]

        # 3：锁票成功 14：出票成功 13：出票失败 2：正在出票
        raw_order = ""
        if state == 13:
            result_info.update({
                "result_code": 2,
                "result_msg": state,
            })
        elif state in [2, 3]:
            raw_order = detail["ticketOrderNo"]
            result_info.update({
                "result_code": 4,
                "result_msg": state,
            })
        elif state== 14:
            raw_order = detail["ticketOrderNo"]
            pick_msg = detail["pickTicketInfo"]
            result_info.update({
                "result_code": 1,
                "result_msg": state,
                "pick_code_list": ["null"],
                "pick_msg_list": [pick_msg],
            })
        if raw_order != order.raw_order_no:
            order.modify(raw_order_no=raw_order)
        return result_info

    def do_refresh_line(self, line):
        result_info = {
            "result_msg": "",
            "update_attrs": {},
        }
        params = {
            "departure": line.s_city_name,
            "dptCode": line.s_city_code,
            "destination": line.d_city_name,
            "desCode": line.d_city_code,
            "dptTime": line.drv_date,
            "stationCode": "",
            "queryType": "1",
            "exParms": ""
        }
        fd = self.post_data_templ("U0103", json.dumps(params))
        r = requests.post(line_url, data=urllib.urlencode(fd), headers=self.post_headers())
        res = r.json()
        now = dte.now()
        if res["code"] != 1100:
            result_info.update(result_msg="error response: %s" % res["message"],
                               update_attrs={"left_tickets": 0, "refresh_datetime": now})
            return result_info

        update_attrs = {}
        for d in res["data"]:
            dpt_time = d["dptTime"]
            lst = dpt_time.split(":")
            if len(lst) == 3:
                dpt_time = ":".join(lst[:2])
            drv_datetime = dte.strptime("%s %s" % (d["dptDate"], dpt_time), "%Y-%m-%d %H:%M")
            line_id_args = {
                "s_city_name": line.s_city_name,
                "d_city_name": line.d_city_name,
                "s_sta_name": d["dptStation"],
                "d_sta_name": d["arrStation"],
                "crawl_source": line.crawl_source,
                "drv_datetime": drv_datetime,
            }
            line_id = md5("%(s_city_name)s-%(d_city_name)s-%(drv_datetime)s-%(s_sta_name)s-%(d_sta_name)s-%(crawl_source)s" % line_id_args)
            try:
                obj = Line.objects.get(line_id=line_id)
            except Line.DoesNotExist:
                continue
            extra_info = {"exData1": d["exData1"], "exData2": d["exData2"]}
            info = {
                "full_price": float(d["ticketPrice"]),
                "fee": float(d["fee"]),
                "left_tickets": int(d["ticketLeft"] or 0),
                "refresh_datetime": now,
                "extra_info": extra_info,
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

    def get_pay_page(self, order, valid_code="", session=None, pay_channel="alipay" ,**kwargs):
        if order.status in [STATUS_LOCK_RETRY, STATUS_WAITING_LOCK]:
            self.lock_ticket(order)
        order.reload()

        if order.status == STATUS_WAITING_ISSUE:
            return {"flag": "url", "content": order.pay_url}

