#!/usr/bin/env python
# encoding: utf-8

import requests
import json
import urllib

import datetime
import random
from lxml import etree
from bs4 import BeautifulSoup

from app.constants import *
from app.flow.base import Flow as BaseFlow
from app.models import Bus365AppRebot, Line, Bus365WebRebot
from datetime import datetime as dte
from app.utils import md5
from app import order_log, line_log


class Flow(BaseFlow):

    name = "bus365"

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
        with Bus365AppRebot.get_and_lock(order) as rebot:
#             if not rebot.test_login_status():
#                 rebot.login()
#                 rebot.reload()
            line = order.line
            try:
                rebot.recrawl_shiftid(line)
            except:
                lock_result.update(result_code=2,
                                   source_account=rebot.telephone,
                                   result_reason="源站刷新线路错误，锁票重试")
                return lock_result
            line = Line.objects.get(line_id=order.line.line_id)
            order.line = line
            order.save()

            lock_result.update(source_account=rebot.telephone)
            if order.line.left_tickets == 0:
                lock_result.update(result_reason="该条线路余票不足", result_code=0)
                return lock_result
            data = {
                "order.scheduleid": line.shift_id,
                "getinsure": "1",
                "order.seattype": line.seat_type,
                "order.userid": rebot.user_id,
                "order.username": rebot.telephone,
                "order.passengername": order.contact_info['name'],
                "order.passengerphone": order.contact_info['telephone'],
                "order.passengeremail": '',
                "order.idnum": '',
                "order.issavepassenger":"1",
                "token": json.dumps({"clienttoken": rebot.client_token, "clienttype":"android"}),
                "clienttype": "android",
                "usertoken": rebot.client_token,
                "deviceid": rebot.deviceid,
                "clientinfo": rebot.clientinfo,
              }
            riders = order.riders
            count = len(riders)
            pas_list = []
            for i in range(count):
                tmp = {
                    "tickettype": '1',
                    "cardtype": '1',
                    "phonenum": riders[i]["telephone"],
                    "idnum": riders[i]["id_number"],
                    "premiumcount": "0",
                    "premiumstate": "0",
                    "name": riders[i]["name"],
                }
                pas_list.append(tmp)
            data['order.passengers'] = json.dumps(pas_list)
            res = self.send_lock_request(order, rebot, data=data)
            if isinstance(res, list):
                res = res[0]
            if res.has_key('getwaylist'):
                del res['getwaylist']
            lock_result.update({
                "source_account": rebot.telephone,
            })
            if res.get('order', ''):
                expire_time = dte.now()+datetime.timedelta(seconds=20*60)
                lock_result.update({
                    "result_code": 1,
                    "result_reason": "",
                    "pay_url": "",
                    "raw_order_no": res['order']['orderno'],
                    "expire_datetime": expire_time,
                    "lock_info": res,
                    "pay_money": float(res['order']['totalprice']),
                })
            else:
                errmsg = res.get('message', '')
                for s in ['班次已停售']:
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

    def send_lock_request(self, order, rebot, data):
        """
        单纯向源站发请求
        """
        order_url = "http://%s/order/createorder" % order.line.extra_info['start_info']['netname']
        headers = rebot.http_header()
        r = rebot.http_post(order_url, data=data, headers=headers)
        ret = r.json()
        return ret

    def send_orderDetail_request(self, rebot, order=None, lock_info=None):
        url = "http://www.bus365.com/order/nonmember/phone/0"
        headers = rebot.http_header()
        param = {
            "orderno": order.raw_order_no,
            "passengerphone": order.contact_info['telephone'],
            "token": json.dumps({"clienttoken": rebot.client_token, "clienttype":"android"}),
            "clienttype": 'android',
            "usertoken": rebot.client_token
        }
        order_detail_url = url + '?'+urllib.urlencode(param)
        r = rebot.http_get(order_detail_url, headers=headers)
        ret = r.json()
        return {
            "state": ret['status'],
        }

    def do_refresh_issue(self, order):
        result_info = {
            "result_code": 0,
            "result_msg": "",
            "pick_code_list": [],
            "pick_msg_list": [],
        }
        rebot = Bus365AppRebot.objects.get(telephone=order.source_account)
        ret = self.send_orderDetail_request(rebot, order=order)

        state = ret["state"]
        order_status_mapping = {
                1: "购票成功",
                2: "出票失败",
                3: "取消购票",
                4: "取消购票",
                5: "取消购票",
                }
        if state == 1: #"出票成功":
            code_list = []
            msg_list = []
            dx_templ = DUAN_XIN_TEMPL[SOURCE_BUS365]
            tele_list = []
            for i in order.riders:
                tele_list.append(i["telephone"][-4:])
            dx_info = {
                "start": "%s(%s)" % (order.line.s_city_name, order.line.s_sta_name),
                "end": order.line.d_sta_name,
                "time": order.drv_datetime.strftime("%Y-%m-%d %H:%M"),
                "order_no": order.raw_order_no,
                "amount": order.ticket_amount,
                "tele_list": ",".join(tele_list)
            }
            code_list.append('无需取票密码')
            msg_list.append(dx_templ % dx_info)
            result_info.update({
                "result_code": 1,
                "result_msg": order_status_mapping[state],
                "pick_code_list": code_list,
                "pick_msg_list": msg_list,
            })

        elif state == 0: #"出票中":
            result_info.update({
                "result_code": 4,
                "result_msg": order_status_mapping[state],
            })
        elif state in (2, 3, 4, 5):#取消购票,购票失败,退票成功
            result_info.update({
                "result_code": 2,
                "result_msg": order_status_mapping[state],
            })
        return result_info

    def get_pay_page(self, order, valid_code="", session=None, pay_channel="alipay" ,**kwargs):
        if order.source_account:
            rebot = Bus365WebRebot.objects.get(telephone=order.source_account)
        else:
            rebot = Bus365WebRebot.get_one()
        
#         headers = {
#            "User-Agent": rebot.user_agent or random.choice(BROWSER_USER_AGENT),
#            "Content-Type": "application/x-www-form-urlencoded",
#            "Charset": "UTF-8",
#            }
#         cookies = {}
#         if order.status == STATUS_LOCK_RETRY:
#             self.lock_ticket(order)
# 
#         if order.status == STATUS_WAITING_ISSUE:
#             param = {
#                      "ordertoken": order.lock_info['order']['ordertoken'],
#                      "orderno": order.lock_info['order']['orderno'],
#                      "userid": str(order.lock_info['order']['userid'])
#                      }
#             url = "http://%s/applyorder/payunfinishorder/0"%order.line.extra_info['start_info']['netname']
#             unpay_url = url + '?'+urllib.urlencode(param)
#             r = rebot.http_get(unpay_url, headers=headers, cookies=cookies)
#             gatewayid = 65
#             content = r.content
#             if not isinstance(content, unicode):
#                 content = content.decode('utf-8')
#             if order.raw_order_no in content:
#                 param.update({"gatewayid": gatewayid})
#                 middle_url = "http://%s/ticket/paymentParams/0" % order.line.extra_info['start_info']['netname']
#                 pay_url = middle_url + '?'+urllib.urlencode(param)
#                 r = rebot.http_get(pay_url, headers=headers, cookies=cookies)
#                 content = r.content
#                 if not isinstance(content, unicode):
#                     content = content.decode('utf-8')
#                 params = {}
#                 sel = etree.HTML(content)
#                 for s in sel.xpath("//form[@name='form_payment0']//input"):
#                     k, v = s.xpath("@name"), s.xpath("@value")
#                     if k:
#                         k, v = k[0], v[0] if v else ""
#                         params[k] = v
#                 url = "https://mapi.alipay.com/gateway.do?_input_charset=utf-8"
#                 r = rebot.http_post(url, headers=headers, cookies=cookies, data=params)
#                 if not order.pay_order_no:
#                     order.modify(pay_order_no=raw_order_no)
#                 return {"flag": "html", "content": r.content.decode('gbk')}    

        is_login = rebot.test_login_status()
        if not is_login:
            if valid_code:#  登陆
                key = "pay_login_info_%s_%s" % (order.order_no, order.source_account)
                pwd_info = SOURCE_INFO[SOURCE_BUS365]["pwd_encode_web"]
                data = json.loads(session[key])
                code_url = data["valid_url"]
                headers = data["headers"]
                cookies = data["cookies"]
                module = data["module"]
                empoent = data["empoent"]
                authenticityToken = data["authenticityToken"]
                ismock = data["ismock"]
                data = {
                    "module": module,
                    "empoent": empoent,
                    "authenticityToken": authenticityToken,
                    "ismock": ismock,
                    "user.username": rebot.telephone,
                    "user.verifycode": valid_code,
                    "user.password": pwd_info[rebot.password]
                }
                url = "http://www.bus365.com/user/login"
                r = rebot.http_post(url, data=data, headers=headers, cookies=cookies)
                new_cookies = r.cookies
                content = r.content
                if not isinstance(content, unicode):
                    content = content.decode('utf-8')
                sel = etree.HTML(content)
                ErrorCode = sel.xpath('//*[@id="error_username"]/text()')
                if ErrorCode:
                    ErrorCode = ErrorCode[0].replace('\n', '').replace('\t', '').replace(' ', '')
                if not ErrorCode:
                    is_login = True
                    cookies.update(dict(new_cookies))
                    rebot.modify(cookies=json.dumps(cookies), is_active=True, last_login_time=dte.now(), user_agent=headers.get("User-Agent", ""))
        if is_login:
            if order.status in (STATUS_WAITING_LOCK, STATUS_LOCK_RETRY):
                self.lock_ticket(order)

            if order.status == STATUS_WAITING_ISSUE:
                param = {
                         "ordertoken": order.lock_info['order']['ordertoken'],
                         "orderno": order.lock_info['order']['orderno'],
                         "userid": str(order.lock_info['order']['userid'])
                         }
                url = "http://%s/applyorder/payunfinishorder/0"%order.line.extra_info['start_info']['netname']
                unpay_url = url + '?'+urllib.urlencode(param)
                r = rebot.http_get(unpay_url, headers=headers, cookies=cookies)
                gatewayid = 65
                content = r.content
                if not isinstance(content, unicode):
                    content = content.decode('utf-8')
                if order.raw_order_no in content:
                    param.update({"gatewayid": gatewayid})
                    middle_url = "http://%s/ticket/paymentParams/0" % order.line.extra_info['start_info']['netname']
                    pay_url = middle_url + '?'+urllib.urlencode(param)
                    r = rebot.http_get(pay_url, headers=headers, cookies=cookies)
                    content = r.content + '<script>window.onload=function(){document.form_payment0.submit();}</script>'
                    return {"flag": "html", "content": content}
                    if not isinstance(content, unicode):
                        content = content.decode('utf-8')
                    params = {}
                    sel = etree.HTML(content)
                    for s in sel.xpath("//form[@name='form_payment0']//input"):
                        k, v = s.xpath("@name"), s.xpath("@value")
                        if k:
                            k, v = k[0], v[0] if v else ""
                            params[k] = v
                    url = "https://mapi.alipay.com/gateway.do?_input_charset=utf-8"
                    r = rebot.http_post(url, headers=headers, cookies=cookies, data=params)
                    if not order.pay_order_no:
                        order.modify(pay_order_no=order.raw_order_no)
                    return {"flag": "html", "content": r.content.decode('gbk')}
            else:
                return {"flag": "false", "content": order.lock_info.get('result_reason','')}
#         elif ErrorCode == '验证码不正确':
        else:
            login_form_url = "http://www.bus365.com/login0"
            headers = {
                       "User-Agent": rebot.user_agent or random.choice(BROWSER_USER_AGENT),
                       "Content-Type": "application/x-www-form-urlencoded",
                       "Charset": "UTF-8",
                       }
            r = rebot.http_get(login_form_url, headers=headers)
            sel = etree.HTML(r.content)
            module = sel.xpath('//form[@id="loginForm"]/div[@id="userLogin"]/input[@id="module"]/@value')[0]
            empoent = sel.xpath('//form[@id="loginForm"]/div[@id="userLogin"]/input[@id="empoent"]/@value')[0]
            authenticityToken = sel.xpath('//form[@id="loginForm"]/div[@id="userLogin"]/input[@name="authenticityToken"]/@value')[0]
            ismock = sel.xpath('//form[@id="loginForm"]/div[@id="userLogin"]/input[@name="ismock"]/@value')[0]
            cookies = dict(r.cookies)
            code_url = sel.xpath("//img[@id='mobileImgVa0']/@src")[0]
            #code_url = "http://www.bus365.com/"code_url.split('?')[0]+"?d=0.%s"% random.randint(1, 10000)
            code_url = "http://www.bus365.com"+code_url
            r = rebot.http_get(code_url, headers=headers, cookies=cookies)
            cookies.update(dict(r.cookies))
            data = {
                "cookies": cookies,
                "headers": headers,
                "valid_url": code_url,
                "module": module,
                "empoent": empoent,
                "authenticityToken": authenticityToken,
                "ismock": ismock,
            }
            key = "pay_login_info_%s_%s" % (order.order_no, order.source_account)
            session[key] = json.dumps(data)
            return {"flag": "input_code", "content": ""}

    def do_refresh_line(self, line):
        import urllib2
        result_info = {
            "result_msg": "",
            "update_attrs": {},
        }
        now = dte.now()
#         headers={
#             "User-Agent": "Apache-HttpClient/UNAVAILABLE (java 1.4)",
#             "Content-Type": "application/x-www-form-urlencoded",
#             "Content-Length":623,
#             "accept": "application/json,",
#             "Accept-Encoding": "gzip",
#             "clienttype":"android",
#             "clienttoken": '',
#             "Host": "www.bus365.com",
#             "Connection": 'Keep-Alive'
#         }
        init_params = {
            "token": '{"clienttoken":"","clienttype":"android"}',
            "clienttype": "android",
            "usertoken": ''
            }
        params = {
            "departdate": line.drv_date,
            "departcityid": line.extra_info['start_info']['id'],
            "reachstationname": line.d_city_name
        }
        params.update(init_params)
        url = "http://%s/schedule/searchscheduler2/0" % line.extra_info['start_info']['netname']
        line_url = "%s?%s" % (url, urllib.urlencode(params))
#         proxies = {
#         'http': 'http://192.168.1.33:8888',
#         'https': 'http://192.168.1.33:8888',
#         }
#         r = requests.get(line_url, headers=headers)
        
#         proxy = urllib2.ProxyHandler(proxies)
#         opener = urllib2.build_opener(proxy)
#         urllib2.install_opener(opener)
        request = urllib2.Request(line_url)
        request.add_header('User-Agent', "Apache-HttpClient/UNAVAILABLE (java 1.4)")
        request.add_header('Content-type', "application/x-www-form-urlencoded")
        request.add_header('accept', "application/json,")
        request.add_header('clienttype', "android")
        request.add_header('clienttoken', "")

        response = urllib2.urlopen(request, timeout=30)
        res = json.loads(response.read())
        update_attrs = {}
        for d in res['schedules']:
            if int(d['iscansell']) == 1:
                drv_datetime = dte.strptime("%s %s" % (line.drv_date, d['departtime'][0:-3]), "%Y-%m-%d %H:%M")
                line_id_args = {
                    "s_city_name": line.s_city_name,
                    "d_city_name": line.d_city_name,
                    "s_sta_name": d["busshortname"],
                    "d_sta_name": d["stationname"],
                    "bus_num": d["schedulecode"],
                    "crawl_source": line.crawl_source,
                    "drv_datetime": drv_datetime,
                }
                line_id = md5("%(s_city_name)s-%(d_city_name)s-%(drv_datetime)s-%(s_sta_name)s-%(d_sta_name)s-%(crawl_source)s" % line_id_args)
                try:
                    obj = Line.objects.get(line_id=line_id)
                except Line.DoesNotExist:
                    continue
                info = {
                    "full_price": float(d["fullprice"]),
                    "fee": 3,
                    "left_tickets": int(d["residualnumber"]),
                    "refresh_datetime": now,
                    "shift_id": d['id'],
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
