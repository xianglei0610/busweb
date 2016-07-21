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
from tasks import issued_callback


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
        contact_name = order.contact_info["name"]
        if contact_name.isdigit():
            msg = u"姓名是数字，切换到广东省网下单"
            order.modify(line=Line.objects.get(line_id=order.line.check_compatible_lines().get("gdsw", "")),crawl_source='gdsw')
            lock_result.update({
                "result_code": 2,
                "source_account": '',
                "result_reason":  msg
            })
            return lock_result
        try:
            order.contact_info["name"].decode('utf8').encode('gb2312')
        except:
            msg = u"汉字转换错误，切换到广东省网下单"
            order.modify(line=Line.objects.get(line_id=order.line.check_compatible_lines().get("gdsw", "")),crawl_source='gdsw')
            lock_result.update({
                "result_code": 2,
                "source_account": '',
                "result_reason":  msg
            })
            return lock_result
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
        href = line.extra_info['query_url']
        href = href.replace('num=1', 'num=%s' % num)
        msg = ''
        full_price = 0
        for i in range(50):
            param = {}
            for s in href.split(";")[0][15:-1].split("?")[1].split("&"):
                k, v = s.split("=")
                param[k] = v.encode('gb2312')
            query_url = "%s%s" % ('http://www.mp0769.com/orderlist.asp?', urllib.urlencode(param))
            req = urllib2.Request(query_url, headers=headers)
            result = urllib2.urlopen(req)
            content = result.read()
            res = content.decode('gbk')
            if '非法操作' in res:
                query_url = "http://www.mp0769.com/" + href.split(";")[0][15:-1]
                req = urllib2.Request(query_url, headers=headers)
                result = urllib2.urlopen(req)
                content = result.read()
                res = content.decode('gbk')
            check_url = re.findall("window.location.href=(.*);", res)[0][1:-1]
            check_url = "http://www.mp0769.com/" + check_url
            param = {}
            for s in check_url.split("?")[1].split("&"):
                k, v = s.split("=")
                param[k] = v.encode('gb2312')
            trade_no = param['trade_no']
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
                ct_price = params['ct_price']
                full_price = params['ct_price']
                left_tickets = params['ct_accnum']
                end_station = params['ct_stname'].decode('gbk')
                break
        if float(full_price) > 0 and float(full_price) == float(order.order_price) :
            agree_url = sel.xpath('//form[@id="Form1"]/@action')[0]
            agree_url = "http://www.mp0769.com/" + agree_url
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
            save_url = sel.xpath("//form[@name='register']/@action")[0]
            save_url = "http://www.mp0769.com/" + save_url
            data = urllib.urlencode(params)
            req = urllib2.Request(save_url, data, headers=headers)
            result = urllib2.urlopen(req)
            content = result.read()
            sel = etree.HTML(content)
            params = {}
            T_Amt = sel.xpath("//input[@id='T_Amt']/@value")[0]      #票款
            T_Pnum = sel.xpath("//input[@id='T_Pnum']/@value")[0]    #购买张数
            T_Price = sel.xpath("//input[@id='T_Price']/@value")[0]  #票价
            T_Qamt = sel.xpath("//input[@id='T_Qamt']/@value")[0]    #服务费
            T_Zamt = sel.xpath("//input[@id='T_Zamt']/@value")[0]    #总金额
            ticketPassword = str(random.randint(100000, 999999))
            params = {
                    "T_Address": "",
                    "T_Amt": T_Amt,
                    "T_Email": "",
                    "T_Mobile": order.contact_info["telephone"],
                    "T_Password": ticketPassword,
                    "T_Password1": ticketPassword,
                    "T_Pnum": T_Pnum,
                    "T_Price": T_Price,
                    "T_Qamt": T_Qamt,
                    "T_TrueName": order.contact_info["name"].decode('utf8').encode('gb2312'),
                    "T_Usercard": order.contact_info["id_number"],
                    "T_Usercard1": order.contact_info["id_number"],
                    "T_Zamt": T_Zamt,
                    "T_Zjname": '1',  #取票凭证 身份证 1
                    "submit":  u'提交[在线支付票款]'.encode('gb2312')
                    }
            send_url = sel.xpath("//form[@name='form8']/@action")[0]      #url
            send_url = "http://www.mp0769.com/"+send_url
            data = urllib.urlencode(params)
            req = urllib2.Request(send_url, data, headers=headers)
            result = urllib2.urlopen(req)
            content = result.read()
            pay_url = re.findall('window.open \((.*),', content)[0][1:-1]
            pay_url = "http://www.mp0769.com/" + pay_url
            order.modify(extra_info={"ticketPassword": ticketPassword})
#             r = requests.get(pay_url)
#             content = r.content.decode('gbk')
#             print content
#             order.modify(extra_info={'pay_content':content})
#             ua = random.choice(BROWSER_USER_AGENT)
#             headers = {
#                    "User-Agent": ua,
#                    }
#             req = urllib2.Request(pay_url, data, headers=headers)
#             result = urllib2.urlopen(req)
#             content = result.read().decode('gbk')
#             print content
#             order.modify(extra_info={'pay_content':content})
        else:
            msg = u"未获取到线路的金额和余票"
            order.modify(line=Line.objects.get(line_id=order.line.check_compatible_lines().get("gdsw", "")),crawl_source='gdsw')
            lock_result.update({
                "result_code": 2,
                "source_account": '',
                "result_reason":  msg
            })
            return lock_result
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
        param = {
                "action": 'queryclick',
                "cardID": order.contact_info["id_number"],
                "type": '1',
                "Verifycode": code
        }
        order_url = "http://www.mp0769.com/orderdisp.asp?"
        order_url = "%s%s" % (order_url, urllib.urlencode(param))
        req = urllib2.Request(order_url, headers=headers)
        content = urllib2.urlopen(req).read()
        content = content.decode('gbk')
        sel = etree.HTML(content)
        order_list = sel.xpath('//table[@bordercolor="#2c6c90"]/tbody/tr')
        res = {}
        if order_list:
            for i in order_list[1:]:
                order_no = i.xpath('td')[0].xpath('text()')[0]
                status = i.xpath('td')[7].xpath('font/text()')[0].replace('\r\n', '').replace('\t',  '').replace(' ',  '')
                if order_no == order.raw_order_no:
                    res.update({"status": status})
                    break
        return res

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

        code_list, msg_list = [], []
        status = ret.get("status", None)
        order_status_mapping = {
                u"订票成功": "订票成功",
                u"订票失败": "订单失效",
                u'正在出票': "正在出票",
                }
        if status in (u"订票成功",):
            dx_templ = DUAN_XIN_TEMPL[SOURCE_DGKY]
            ticketPassword = order.extra_info.get("ticketPassword", '')
            dx_info = {
                "start": "%s(%s)" % (order.line.s_city_name, order.line.s_sta_name),
                "end": order.line.d_sta_name,
                "time": order.drv_datetime.strftime("%Y-%m-%d %H:%M"),
                "raw_order": order.raw_order_no,
                "code": ticketPassword,
            }
            if ticketPassword:
                code_list.append(ticketPassword)
            else:
                code_list.append('无需取票密码')
            msg_list.append(dx_templ % dx_info)
            result_info.update({
                "result_code": 1,
                "result_msg": "",
                "pick_code_list": code_list,
                "pick_msg_list": msg_list,
            })
        elif status in (u"正在出票",):
            result_info.update({
                "result_code": 4,
                "result_msg": order_status_mapping[status],
            })
#         elif status in (u"订票失败",):
#             result_info.update({
#                 "result_code": 2,
#                 "result_msg": order_status_mapping[status],
#             })
        return result_info

    def do_refresh_line(self, line):
        now = dte.now()
        result_info = {
            "result_msg": "",
            "update_attrs": {},
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
        try:
            result = urllib2.urlopen(req)
        except:
            result_info.update(result_msg="timeout default 1", update_attrs={"left_tickets": 5, "refresh_datetime": now})
            return result_info
        code = ''
        init_url = "http://www.mp0769.com/bccx.asp?"
        params = {
             "action": "queryclick",
             "Depot": line.s_sta_id,
             "date": line.drv_date,
             "Times": line.drv_time.split(':')[0],
             "num": "1",
             "Verifycode": code,
             "tanchu": 1
             }
        init_url_param = "%s%s" % (init_url, urllib.urlencode(params))
        station_url = init_url_param + '&station=%s' % json.dumps(line.d_sta_name).replace('\u','%u')[1:-1]
        try:
            form, sel = self.is_end_station(urllib2, headers, station_url)
        except:
            result_info.update(result_msg="timeout default 5", update_attrs={"left_tickets": 5, "refresh_datetime": now})
            return result_info
        if not form:
            station = sel.xpath('//a')
            for i in station:
                td = i.xpath('font/text()')
                href = i.xpath('@href')[0]
                station_name = td[0].replace('\r\n', '').replace('\t', '').replace(' ',  '')
                if station_name == line.d_sta_name:
                    station_url = "http://www.mp0769.com/cbprjdisp8.asp?"+href
                    try:
                        form, sel = self.is_end_station(urllib2, headers, station_url)
                    except:
                        result_info.update(result_msg="timeout default 5", update_attrs={"left_tickets": 5, "refresh_datetime": now})
                        return result_info
        update_attrs = {}
        if form:
            sch = sel.xpath('//table[@width="600"]/tr')
            for i in sch[1:]:
                status = i.xpath('td[8]/div/text()')[0].replace('\r\n', '').replace('\t',  '').replace(' ',  '')
                if status != '售票':
                    continue
                bus_num = i.xpath('td[1]/div/text()')[0].replace('\r\n', '').replace('\t',  '').replace(' ',  '')
                drv_date = i.xpath('td[2]/div/text()')[0].replace('\r\n', '').replace('\t',  '').replace(' ',  '')
                drv_date = dte.strftime(dte.strptime(drv_date, '%Y-%m-%d'),'%Y-%m-%d')
                drv_time = i.xpath('td[3]/div/text()')[0].replace('\r\n', '').replace('\t',  '').replace(' ',  '')
                start_station = i.xpath('td[4]/div/text()')[0].replace('\r\n', '').replace('\t',  '').replace(' ',  '')
                #end_station = i.xpath('td[5]/div/text()')[0].replace('\r\n', '').replace('\t',  '').replace(' ',  '')
                href = i.xpath('td[9]/div/a/@onclick')[0]
                if 'javascript:alert' in href:
                    continue
                full_price = 0
                left_tickets = 5
                end_station = line.d_sta_name
                try:
                    for i in range(5):
                        param = {}
                        for s in href.split(";")[0][15:-1].split("?")[1].split("&"):
                            k, v = s.split("=")
                            param[k] = v.encode('gb2312')
                        query_url = "%s%s" % ('http://www.mp0769.com/orderlist.asp?', urllib.urlencode(param))
                        req = urllib2.Request(query_url, headers=headers)
                        result = urllib2.urlopen(req)
                        content = result.read()
                        res = content.decode('gbk')
                        if '非法操作' in res:
                            query_url = "http://www.mp0769.com/" + href.split(";")[0][15:-1]
                            req = urllib2.Request(query_url, headers=headers)
                            result = urllib2.urlopen(req)
                            content = result.read()
                            res = content.decode('gbk')
                        check_url = re.findall("window.location.href=(.*);", res)[0][1:-1]
                        check_url = "http://www.mp0769.com/" + check_url
                        param = {}
                        for s in check_url.split("?")[1].split("&"):
                            k, v = s.split("=")
                            param[k] = v.encode('gb2312')
                        order_url = "http://www.mp0769.com/orderlist.asp?"
                        order_url = "%s%s" % (order_url, urllib.urlencode(param))
                        req = urllib2.Request(order_url, headers=headers)
                        result = urllib2.urlopen(req)
                        content = result.read().decode('gbk')
                        sel = etree.HTML(content)
                        params = {}
                        for s in sel.xpath("//form[@id='Form1']//input"):
                            k, v = s.xpath("@name"), s.xpath("@value")
                            if k:
                                k, v = k[0], v[0] if k else ""
                                params[k] = v.encode('gb2312')
                        if not params or int(params.get('ct_price', 0)) == 0:
                            continue
                        else:
                            full_price = params['ct_price']
                            left_tickets = params['ct_accnum']
                            end_station = params['ct_stname'].decode('gbk')
                            break
                except:
                    end_station = line.d_sta_name

                drv_datetime = dte.strptime("%s %s" % (drv_date, drv_time), "%Y-%m-%d %H:%M")
                line_id_args = {
                    "s_city_name": line.s_city_name,
                    "d_city_name": line.d_city_name,
                    "s_sta_name": start_station,
                    "d_sta_name": end_station,
                    "crawl_source": line.crawl_source,
                    "drv_datetime": drv_datetime,
                }
                line_id = md5("%(s_city_name)s-%(d_city_name)s-%(drv_datetime)s-%(s_sta_name)s-%(d_sta_name)s-%(crawl_source)s" % line_id_args)
                try:
                    obj = Line.objects.get(line_id=line_id)
                except Line.DoesNotExist:
                    continue
                extra_info = {"query_url": href}
                info = {
                    "fee": 0,
                    "left_tickets": int(left_tickets or 0),
                    "refresh_datetime": now,
                    "extra_info": extra_info,
                }
                if full_price > 0:
                    info.update({"full_price": full_price})
                if line_id == line.line_id:
                    update_attrs = info
                else:
                    obj.update(**info)
        if not update_attrs:
            result_info.update(result_msg="no line info", update_attrs={"left_tickets": 0, "refresh_datetime": now})
        else:
            result_info.update(result_msg="ok", update_attrs=update_attrs)
        return result_info

    def is_end_station(self, urllib2, headers, station_url):
        req = urllib2.Request(station_url, headers=headers)
        result = urllib2.urlopen(req)
        content = result.read()
        content = content.decode('gbk')
        sel = etree.HTML(content)
        form = sel.xpath('//form[@method="Post"]/@action')
        return form, sel

    def get_pay_page(self, order, valid_code="", session=None, pay_channel="alipay" ,**kwargs):
        if order.status == STATUS_WAITING_ISSUE:
            res = self.request_order_detail(order)
            if not res:
                msg = u'未获取源站订单号，不允许支付'
                order.modify(status=STATUS_LOCK_RETRY,
                             line=Line.objects.get(line_id=order.line.check_compatible_lines().get("gdsw", "")),
                             crawl_source='gdsw')
                order.on_lock_retry(reason=msg)
                order.reload()
            else:
                r = requests.get(order.pay_url)
                content = r.content.decode('gbk')
                res = re.findall(r"alert\('(.*?)'\);", content)
                if res:
                    errmsg = res[0]
                    if u"您的订单已过有效期" in errmsg:
                        order.modify(status=STATUS_LOCK_RETRY)
                        order.on_lock_retry(reason=errmsg)
                        return {"flag": "error", "content": '重新打开'}
                    else:
                        if u'不可预售' in errmsg:
                            self.close_line(order.line, reason=errmsg)
                        order.modify(status=STATUS_LOCK_FAIL)
                        order.on_lock_fail(reason=errmsg)
                        issued_callback.delay(order.order_no)
                else:
                    order.update(pay_channel='alipay')
                    return {"flag": "url", "content": order.pay_url}
        if order.status in [STATUS_LOCK_RETRY, STATUS_WAITING_LOCK]:
            self.lock_ticket(order)
        order.reload()
        if order.status == STATUS_WAITING_ISSUE:
            return {"flag": "error", "content": '重新打开'}



