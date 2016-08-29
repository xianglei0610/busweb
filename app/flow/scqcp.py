# -*- coding:utf-8 -*-

import urllib2
import urllib
import requests
import json
import pytesseract
import cStringIO
import random
import urlparse
import datetime
import time
import re

from app.constants import *
from app.flow.base import Flow as BaseFlow
from app.models import ScqcpAppRebot, ScqcpWebRebot
from datetime import datetime as dte
from PIL import Image
from lxml import etree
from app.utils import md5
from tasks import issued_callback

class Flow(BaseFlow):
    name = "scqcp"

    def do_lock_ticket(self, order):
        return self.do_lock_ticket_by_web(order)

        rebot = order.get_lock_rebot()
        tickets = []
        for r in order.riders:
            lst = [r["id_number"], r["name"], r["telephone"], "0", "0"]
            tickets.append("|".join(lst))
        data = {
            "carry_sta_id": order.line.s_sta_id,
            "stop_name": order.line.d_city_name,
            "str_date": "%s %s" % (order.line.drv_date, order.line.drv_time),
            "sign_id": order.line.extra_info["sign_id"],
            "phone_num": order.contact_info["telephone"],
            "buy_ticket_info": "$".join(tickets),
            "open_id": rebot.open_id,
        }
        ret = self.send_lock_request(rebot, data)
        lock_result = {
            "lock_info": ret,
            "source_account": rebot.telephone,
            "pay_money": 0,
        }
        if ret["status"] == 1:
            pay_url = "http://www.scqcp.com/ticketOrder/redirectOrder.html?pay_order_id=%s" % ret["pay_order_id"]
            total_price = 0
            for ticket in ret["ticket_list"]:
                total_price += ticket["server_price"]
                total_price += ticket["real_price"]
            lock_result.update({
                "result_code": 1,
                "result_reason": "",
                "pay_url": pay_url,
                "raw_order_no": ",".join(ret["web_order_id"]),
                "expire_datetime": dte.strptime(ret["expire_time"], "%Y-%m-%d %H:%M:%S"),
                "pay_money": total_price,
            })
        else:
            lock_result.update({
                "result_code": 0,
                "result_reason": ret["msg"],
                "pay_url": "",
                "raw_order_no": "",
                "expire_datetime": "",
            })
        return lock_result

    def do_lock_ticket_by_web(self, order):
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
        is_login = rebot.test_login_status()
        if not is_login:
            for i in range(3):
                if rebot.login() == "OK":
                    is_login = True
                    break
                rebot = order.change_lock_rebot()

        if not is_login:
            lock_result.update(result_code=2,
                               source_account=rebot.telephone,
                               result_reason="账号未登陆")
            return lock_result

        try:
            res = self.request_query_token_by_web(rebot, order)
        except:
            rebot.modify(ip="")
            rebot.modify(cookies="{}")
            lock_result.update(result_code=2,
                               source_account=rebot.telephone,
                               result_reason="获取token失败")
            return lock_result
        if res.get('status', '') == 0:
            token = res.get('token', '')
        elif res.get('status', '') == 1:
            msg = res.get('msg', '')
            if u'输入参数不对，请参考接口文档' in msg or u'维护升级' in msg or 'connect timed out' in msg:
                rebot.modify(ip="")
                rebot.modify(cookies="{}")
                lock_result.update(result_code=2,
                                   source_account=rebot.telephone,
                                   result_reason="获取token失败2:%s"%msg)
                return lock_result
            lock_result.update(result_code=0,
                               source_account=rebot.telephone,
                               result_reason="获取token失败:"+msg)
            return lock_result
        ret = self.send_lock_request_by_web(rebot, order, token)
        if not ret:
            rebot.modify(ip="")
            rebot.modify(cookies="{}")
            rebot = order.change_lock_rebot()
            lock_result.update(result_code=2,
                               source_account=rebot.telephone,
                               result_reason="锁票异常")
            return lock_result
        lock_result.update({
                            "lock_info": ret,
                            "source_account": rebot.telephone,
                            "pay_money": 0,
                            })
        if ret.get("status", '') == 1:
            expire_datetime = dte.now()+datetime.timedelta(seconds=28*60)
            lock_result.update({
                "result_code": 1,
                "result_reason": "",
                "pay_url": ret["pay_url"],
                "raw_order_no": "",
                "expire_datetime": expire_datetime,
                "pay_money": order.order_price,
            })
        else:
            errmsg = ret['msg']
            if u"参数错误" in errmsg:
                contact_name = order.contact_info['name'].strip()
                phone_num = order.contact_info['telephone']
                msg = ''
                if contact_name.isdigit():
                    name_list = []
                    url_list = [
                            "http://zhao.resgain.net/name_list.html",
                            "http://shen.resgain.net/name_list.html",
                            ]
                    for url in url_list:
                        r = requests.get(url, headers={"User-Agent": "Chrome3.8"})
                        name_list.extend(re.findall(r"/name/(\S+).html", r.content))
                    name = random.choice(name_list)
                    msg = '更改联系人姓名: %s=>%s' % (contact_name, name)
                    order.contact_info['name'] = name
                    order.save()
                    order.reload()
                not_support_list = ['171', '177', '147', '178', '176', '170', '173', '186', '187']
                if phone_num[0:3] in not_support_list:
                    if rebot.telephone[0:3] not in not_support_list:
                        telephone = rebot.telephone
                    else:
                        telephone = random.choice(["13267109876", "13560750217","18656022990", "15914162537", "13510175093"])
                    msg = '更改联系人手机号: %s=>%s' % (phone_num, telephone)
                    order.contact_info['telephone'] = telephone
                    order.save()
                    order.reload()
                lock_result.update({
                        "result_code": 2,
                        "source_account": rebot.telephone,
                        "result_reason": errmsg,
                    })
                if msg:
                    lock_result.update({
                        "result_reason": ret.get("msg", '') + ":" + msg,
                    })
                return lock_result
            flag = False
            for i in [u"执行方法GetSchSeatsNo出错"]:
                if i in errmsg:
                    flag = True
                    break
            if flag:
                lock_result.update({
                    "result_code": 2,
                    "source_account": rebot.telephone,
                    "result_reason": ret.get("msg", '') or ret,
                })
                return lock_result

            for s in ["余票不足", "只能预售2小时之后的票", "余位不够", "已售完",
                      "超出最大座位数","已停售",'不允许远程售票',"不在网上销售"]:
                if s in errmsg:
                    self.close_line(order.line, reason=errmsg)
                    break

            lock_result.update({
                "result_code": 0,
                "result_reason": ret['msg'],
                "pay_url": "",
                "raw_order_no": "",
                "expire_datetime": "",
            })
        return lock_result

    def request_query_token_by_web(self, rebot, order):
        url = "http://scqcp.com/userCommon/createTicketOrder.html"
        headers = rebot.http_header()
        new_headers = headers
        if new_headers.has_key('Content-Type'):
            del new_headers['Content-Type']
        params = {
                "carry_sta_id": order.line.s_sta_id,
                "str_date": "%s %s" % (order.line.drv_date, order.line.drv_time),
                "sign_id": order.line.extra_info['sign_id'],
                "stop_name": order.line.d_city_name,
                }
        url = "%s?%s" % (url, urllib.urlencode(params))
        try:
            r = rebot.http_get(url, headers=new_headers, timeout=15)
            sel = etree.HTML(r.content)
            token = sel.xpath('//form[@id="ticket_with_insurant"]/input[@name="token"]/@value')[0]
            return {"status": 0, 'token': token}
        except:
            rebot.modify(ip='')
            r = rebot.http_get(url, headers=new_headers, timeout=70, allow_redirects=False)
            location_url = r.headers.get('location', '')
            res = {}
            if location_url:
                result = urlparse.urlparse(location_url)
                params = urlparse.parse_qs(result.query, True)
                errorMsg = params.get('errorMsg', [])
                res = {"status": 1, 'msg': errorMsg[0].decode('utf8')}
            return res

    def send_lock_request(self, rebot, data):
        """
        单纯向源站发锁票请求
        """
        url = urllib2.urlparse.urljoin(SCQCP_DOMAIN, "/api/v1/telecom/lock")
        headers = {
            "User-Agent": rebot.user_agent,
            "Authorization": rebot.token,
            "Content-Type": "application/json; charset=UTF-8",
        }
        r = rebot.http_post(url, data=urllib.urlencode(data), headers=headers)
        ret = r.json()
        return ret

    def send_lock_request_by_web(self, rebot, order, token):
        data = {
          "sdfgfgfg": "on",
          "contact_name": order.contact_info['name'].strip(),
          "phone_num": order.contact_info['telephone'],
          "contact_card_num": "",
          "sign_id": order.line.extra_info['sign_id'],
          "carry_sta_id": order.line.s_sta_id,
          "drv_date_time": "%s %s" % (order.line.drv_date, order.line.drv_time),
          "stop_name": order.line.d_city_name,
          "token": token,
          "is_act": "",
          "passenger_num": "",
          "is_save_contact_person": "false"
          }
        riders = order.riders
        count = len(riders)
        data['passenger_num'] = 'passenger_num%s' % str(count)
        tmp = {}
        for i in range(count):
            tmp = {
                "birthday%s" % (i+1): "%s-%s-%s" % (riders[i]["id_number"][6:10],riders[i]["id_number"][10:12],riders[i]["id_number"][12:14]),
                "bring_child%s" % (i+1): '0',
                "passenger_card_num%s" % (i+1): riders[i]["id_number"],
                "passenger_card_type%s" % (i+1): "id_card",
                "passenger_name%s" % (i+1): riders[i]["name"],
                "passenger_ticket_type%s" % (i+1): "0",
            }
            data.update(tmp)
        headers = rebot.http_header()
        url = 'http://scqcp.com/ticketOrder/lockTicket.html'
        r = rebot.http_post(url, data=urllib.urlencode(data), headers=headers, cookies=json.loads(rebot.cookies),timeout=60,allow_redirects=False)
        location_url = r.headers.get('location', '')
        res = {}
        if location_url:
            result = urlparse.urlparse(location_url)
            params = urlparse.parse_qs(result.query, True)
            pay_order_id = params.get('pay_order_id', [])
            errorMsg = params.get('errorMsg', [])
            if pay_order_id:
                res = {"status": 1, "pay_url": location_url, 'pay_order_id': pay_order_id[0]}
            elif errorMsg:
                res = {"status": 0, 'msg': errorMsg[0].decode('utf8')}
        return res

    def do_refresh_issue(self, order):
        return self.do_refresh_issue_by_web(order)
        result_info = {
            "result_code": 0,
            "result_msg": "",
            "pick_code_list": [],
            "pick_msg_list": [],
        }
        if not self.need_refresh_issue(order):
            result_info.update(result_msg="状态未变化")
            return result_info

        rebot = ScqcpAppRebot.objects.get(telephone=order.source_account)
        tickets = self.send_order_request(order, rebot)
#         if not tickets:
#             result_info.update(result_code=2, result_msg="已过期")
#             return result_info

        status = tickets.values()[0]["order_status"]
        if status == "sell_succeeded":
            code_list, msg_list = [], []
            for tid in order.lock_info["ticket_ids"]:
                code = tickets[tid]["code"]
                if code in code_list:
                    continue
                code_list.append(code)
                dx_tmpl = DUAN_XIN_TEMPL[SOURCE_SCQCP]
                dx_info = {
                    "time": order.drv_datetime.strftime("%Y-%m-%d %H:%M"),
                    "start": order.line.s_sta_name,
                    "end": order.line.d_sta_name,
                    "amount": order.ticket_amount,
                    "code": code,
                }
                msg_list.append(dx_tmpl % dx_info)
            result_info.update({
                "result_code": 1,
                "result_msg": status,
                "pick_code_list": code_list,
                "pick_msg_list": msg_list,
            })
        elif status == "give_back_ticket":
            result_info.update({
                "result_code": 3,
                "result_msg": "源站已退票",
            })
        elif status == "closed":
            result_info.update({
                "result_code": 2,
                "result_msg": status,
            })
        return result_info

    def do_refresh_issue_by_web(self, order):
        result_info = {
            "result_code": 0,
            "result_msg": "",
            "pick_code_list": [],
            "pick_msg_list": [],
        }
        rebot = ScqcpAppRebot.objects.get(telephone=order.source_account)
        res = self.send_order_request_by_web(order, rebot)
        if not order.raw_order_no:
            order.modify(raw_order_no=res['order_no'])
        status = res["order_status"]
        if status in ("sell_succeeded", "succeed", 'completed'):
            code_list, msg_list = [], []
            code = res["pick_code"]
            dx_tmpl = DUAN_XIN_TEMPL[SOURCE_SCQCP]
            dx_info = {
                "time": order.drv_datetime.strftime("%Y-%m-%d %H:%M"),
                "start": order.line.s_sta_name,
                "end": order.line.d_sta_name,
                "amount": order.ticket_amount,
                "code": code,
            }
            code_list = ["%s" % (code)]
            msg_list = [dx_tmpl % dx_info]
            result_info.update({
                "result_code": 1,
                "result_msg": status,
                "pick_code_list": code_list,
                "pick_msg_list": msg_list,
            })
        elif status == "give_back_ticket":
            result_info.update({
                "result_code": 3,
                "result_msg": "源站已退票",
            })
        elif status == "closed":
            result_info.update({
                "result_code": 2,
                "result_msg": status,
            })
        return result_info

    def send_order_request(self, order, rebot):
        return self.send_order_request_by_web(order, rebot)
        data = {"open_id": rebot.open_id}
        uri = "/api/v1/ticket_lines/query_order?_=%s" % time.time()
        url = urllib2.urlparse.urljoin(SCQCP_DOMAIN, uri)
        headers = {
            "User-Agent": rebot.user_agent,
            "Authorization": rebot.token,
            "Content-Type": "application/json; charset=UTF-8",
        }
        r = requests.post(url, data=urllib.urlencode(data), headers=headers)
        ret = r.json()

        ticket_ids = order.lock_info["ticket_ids"]
        amount = len(ticket_ids)
        data = {}
        for d in ret["ticket_list"]:
            if d["ticket_id"] in ticket_ids:
                data[d["ticket_id"]] = d
            if len(data) >= amount:
                break
        return data

    def mock_send_order_request(self, order, rebot):
        ret_info = {}
        for tid in order.lock_info["ticket_ids"]:
            ret_info[tid] = {}
            ret_info[tid]["code"] = "testqp123456"
            ret_info[tid]["order_status"] = "sell_succeeded"
        return ret_info

    def send_order_request_by_web(self, order, rebot):
        url = "http://inner.cdqcp.com/ticket"
        content = {"orderNum": "",
                   "payOrderId": order.lock_info["pay_order_id"],
                   "openId": rebot.open_id
                }
        api = 'getUserOrderTicketInfo'
        params = {}
        params.update(content)
        md5_key = "sdkjfgweysdgfvgvehbfhsdfgvbwjehfsdf"
        params.update({"key": md5_key})

        def get_md5_sign(params):
            ks = params.keys()
            ks.sort()
            rlt = ''
            for k in ks:
                if params[k] == None or len(params[k]) == 0:
                    continue
                rlt = rlt+"&%s=%s" % (k, params[k])
            return md5(rlt[1:]).upper()
        sign = get_md5_sign(params)
        fp = {"head": {
                 "sign": sign,
                 "server": api,
                 "token": "04b8cef68ef4f2d785150eb671999834",
                 "ip": "192.168.3.153",
                 "version": "1.5.1",
                 "signType": "MD5"
                 },
              "body": content
              }
        headers = {
            "User-Agent": 'okhttp/3.2.0',
            "Content-Type": "application/json; charset=UTF-8",
        }
        try:
            r = rebot.http_post(url, data=json.dumps(fp), headers=headers)
            ret = r.json()
        except:
            rebot.modify(ip='')
            r = rebot.http_post(url, data=json.dumps(fp), headers=headers)
            ret = r.json()
        if ret["head"]['statusCode'] == '0000':
            return {
                "order_status": ret["body"].get('state', ''),
                "pick_no": [],
                "pick_code": ret["body"].get('code', ''),
                "order_no": ret["body"].get('webOrderId', ''),
                "drv_date": ret["body"].get('drvDate', ''),
            }

    def do_refresh_line(self, line):
        result_info = {
            "result_msg": "",
            "update_attrs": {},
        }
        now = dte.now()
        if (line.drv_datetime-now).total_seconds() <= 150*60:
            result_info.update(result_msg="time in two hours ", update_attrs={"left_tickets": 0, "refresh_datetime": now})
            return result_info

        content = {
                   "signId": line.extra_info["sign_id"],
                   "carryStaId": line.s_sta_id,
                   "stopName": line.d_city_name,
                   "drvDate": "%s %s" % (line.drv_date, line.drv_time)
                   }
        api = 'getTicketInfo'
        params = {}
        params.update(content)
        md5_key = "sdkjfgweysdgfvgvehbfhsdfgvbwjehfsdf"
        params.update({"key": md5_key})

        def get_md5_sign(params):
            ks = params.keys()
            ks.sort()
            rlt = ''
            for k in ks:
                if params[k] == None or len(params[k]) == 0:
                    continue
                rlt = rlt+"&%s=%s" % (k, params[k])
            return md5(rlt[1:]).upper()
        sign = get_md5_sign(params)
        url = "http://inner.cdqcp.com/ticket"
        fp = {"head": {
                 "sign": sign,
                 "server": api,
                 "token": "04b8cef68ef4f2d785150eb671999834",
                 "ip": "192.168.3.153",
                 "version":"1.5.1",
                 "signType":"MD5"
                 },
              "body": content
              }
        rebot = ScqcpAppRebot.get_one()
        headers = {
            "User-Agent": 'okhttp/3.2.0',
            "Content-Type": "application/json; charset=UTF-8",
        }
        try:
            r = rebot.http_post(url, data=json.dumps(fp), headers=headers, timeout=20)
            ret = r.json()
        except:
            result_info.update(result_msg="scqcp timeout default 15", update_attrs={"left_tickets": 15, "refresh_datetime": now})
            return result_info
        if ret.get("head", {}).get('statusCode', '') == '0000':
            if ret["body"].get('ticketLines', []):
                raw = ret["body"].get('ticketLines', [])[0]
                full_price = float(raw["fullPrice"])
                try:
                    service_price = float(raw["servicePrice"])
                except:
                    service_price = 3.0
                if service_price != float(3):
                    full_price = full_price + service_price - 3
                    service_price = 3
                info = {
                    "full_price": full_price,
                    "fee": service_price,
                    "left_tickets": int(raw["amount"]),
                    "refresh_datetime": now,
                }
                result_info.update(result_msg="ok", update_attrs=info)
            else:  # 线路信息没查到
                result_info.update(result_msg="no line info", update_attrs={"left_tickets": 0, "refresh_datetime": now})
        else:
            result_info.update(result_msg="exception_ok", update_attrs={"left_tickets": 3, "refresh_datetime": now})
        return result_info

    def get_pay_page(self, order, valid_code="", session=None, pay_channel="alipay", bank='',**kwargs):
        rebot = order.get_lock_rebot()
        headers = rebot.http_header()
        new_headers = headers
        if new_headers.has_key('Content-Type'):
            del new_headers['Content-Type']
        is_login = rebot.test_login_status()
        msg = ''
        if not is_login:
            for i in range(3):
                msg = rebot.login()
                if msg == "OK":
                    is_login = True
                    break
        if not is_login:
            if msg in u'用户名或密码错误':
                order.change_lock_rebot()
                order.reload()
            rebot = order.get_lock_rebot()
            rebot.modify(ip='')
            return {"flag": "error", "content": "账号自动登陆失败，请再次重试!"}

        if order.status in [STATUS_LOCK_RETRY, STATUS_WAITING_LOCK]:
            self.lock_ticket(order)
        order.reload()

        if order.status == STATUS_WAITING_ISSUE:
            app_rebot = ScqcpAppRebot.objects.get(telephone=order.source_account)
            res = self.send_order_request_by_web(order, app_rebot)
            if res.get('drv_date', '') != order.drv_datetime.strftime("%Y-%m-%d %H:%M:%S"):
                errmsg = '时间不一致，不允许支付!'
                self.close_line(order.line, reason=errmsg)
                order.modify(status=STATUS_LOCK_FAIL)
                order.on_lock_fail(reason=errmsg)
                issued_callback.delay(order.order_no)
                return {"flag": "error", "content": errmsg}
            r = rebot.http_get(order.pay_url, headers=new_headers, cookies=json.loads(rebot.cookies),timeout=30)
            r_url = urllib2.urlparse.urlparse(r.url)
            if r_url.path in ["/error.html", "/error.htm"]:
                self.lock_ticket_retry(order)
                return {"flag": "error", "content": ''}
            sel = etree.HTML(r.content)
            plateform = pay_channel
            try:
                data = dict(
                    payid=sel.xpath("//input[@name='payid']/@value")[0],
                    bank=bank, #,'BOCB2C',#sel.xpath("//input[@id='s_bank']/@value")[0],
                    plate=sel.xpath("//input[@id='s_plate']/@value")[0],
                    plateform=plateform,
                    qr_pay_mode=0,
                    discountCode=sel.xpath("//input[@id='discountCode']/@value")[0]
                )
            except:
                rebot.modify(ip="")
                rebot.modify(cookies="{}")
                return {"flag": "error", "content": "请重试!"}
            info_url = "http://scqcp.com:80/ticketOrder/middlePay.html"
            cookies = json.loads(rebot.cookies)
            r = rebot.http_post(info_url, data=data, headers=headers, cookies=cookies,timeout=60)
            cookies.update(dict(r.cookies))
#             sel = etree.HTML(r.content)
            try:
                data = self.extract_alipay(r.content)
                pay_money = float(data["total_fee"])
                pay_order_no = data["out_trade_no"]
                if order.pay_money != pay_money or order.pay_order_no != pay_order_no:
                    order.modify(pay_money=pay_money, pay_order_no=pay_order_no, pay_channel='yh')
                jump_url = "https://mapi.alipay.com/gateway.do?_input_charset=utf-8"
                headers.update({"Host": "mapi.alipay.com",
                                "Referer": "http://scqcp.com/ticketOrder/middlePay.html",
                                "Content-Type": "application/x-www-form-urlencoded"
                                })
                res = rebot.http_post(jump_url, data=urllib.urlencode(data), headers=headers, cookies=cookies)
                if u'fastpayLoginForm' not in res.content.decode('gbk'):
                    rebot.modify(ip="")
                    rebot.modify(cookies="{}")
                    return {"flag": "error", "content": "请重试!"}
            except:
                rebot.modify(ip="")
                rebot.modify(cookies="{}")
                return {"flag": "error", "content": "请重试!"}
            return {"flag": "html", "content": r.content}
        return {"flag": "error", "content": "锁票失败, 请重试!"}
        # else:
        #     cookies = json.loads(rebot.cookies)
        #     login_form_url = "http://scqcp.com/login/index.html?%s"%time.time()
        #     r = rebot.http_get(login_form_url, headers=new_headers)
        #     sel = etree.HTML(r.content)
        #     cookies = dict(r.cookies)
        #     code_url = sel.xpath("//img[@id='txt_check_code']/@src")[0]
        #     code_url = code_url.split('?')[0]+"?d=0.%s"% random.randint(1, 10000)
        #     token = sel.xpath("//input[@id='csrfmiddlewaretoken1']/@value")[0]
        #     r = rebot.http_get(code_url, headers=new_headers, cookies=cookies)
        #     cookies.update(dict(r.cookies))
        #     data = {
        #         "cookies": cookies,
        #         "headers": headers,
        #         "valid_url": code_url,
        #         "token": token
        #     }
        #     key = "pay_login_info_%s_%s" % (order.order_no, order.source_account)
        #     session[key] = json.dumps(data)
        #     return {"flag": "input_code", "content": ""}
