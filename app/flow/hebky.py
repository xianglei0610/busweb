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
from app.models import HebkyAppRebot, Line, HebkyWebRebot
from datetime import datetime as dte
from app.utils import md5
from app import order_log


class Flow(BaseFlow):

    name = "hebky"

    def do_lock_ticket(self, order):
        rebot = order.get_lock_rebot()
        if not rebot.test_login_status():
            rebot.login()
            rebot.reload()
        line = order.line
        res = self.send_lock_request(order, rebot)
        if res.has_key('struts.token'):
            del res['struts.token']
        lock_result = {
            "lock_info": res,
            "source_account": rebot.telephone,
            "pay_money": line.real_price()*order.ticket_amount,
        }

        if res['akfAjaxResult'] != '0':
            lock_result.update({
                "result_code": 0,
                "result_reason": res['errorMessage'],
                "pay_url": "",
                "raw_order_no": "",
                "expire_datetime": None,
            })
            return lock_result
        if res['values']['result'] == 'success':
            order_no = res["values"]['orderInfo']['orderMap']['ddh']
            order_log.info("[lock-end] order: %s,account:%s start   query encode orderId request", order.order_no, rebot.telephone)
            try:
                encode_order_detail = self.send_order_request(rebot, lock_info=res)
            except Exception, e:
                order_log.info("[lock-end] order: %s,account:%s start query encode orderId request error %s", order.order_no, rebot.telephone,e)
                rebot.login()
                rebot.reload()
                encode_order_detail = self.send_order_request(rebot, lock_info=res)
            order_log.info("[lock-end] order: %s,account:%s query encode orderId request result:%s", order.order_no, rebot.telephone,encode_order_detail)
            res.update({"encode_orderId": encode_order_detail['orderId']})
            expire_time = dte.now()+datetime.timedelta(seconds=10*60)
            lock_result.update({
                "result_code": 1,
                "result_reason": "",
                "pay_url": "",
                "raw_order_no": order_no,
                "expire_datetime": expire_time,
                "lock_info": res
            })
        else:
            errmsg = res['values']['result'].replace("\r\n", " ")
            for s in ["剩余座位数不足"]:
                if s in errmsg:
                    self.close_line(line, reason=errmsg)
                    break
            lock_result.update({
                "result_code": 0,
                "result_reason": res['values']['result'],
                "pay_url": "",
                "raw_order_no": "",
                "expire_datetime": None,
            })
        return lock_result

    def send_lock_request(self, order, rebot):
        """
        单纯向源站发请求
        """
        line = order.line
        data = {
           "busInfoModel.fcsk": line.drv_time,
           "busInfoModel.ddz": line.d_sta_name,
           "busInfoModel.scdbm": line.s_sta_id,
#                "busInfoModel.bcjtbm": line.extra_info['busCompanyCode'],
           "busInfoModel.scd": line.s_sta_name,
           "busInfoModel.fcrq": line.drv_date,
           "busInfoModel.ddzbm": line.d_sta_id,
           "busInfoModel.bcbh": line.bus_num,
           "busInfoModel.sfzx": line.extra_info['busCodeType'],
           "busInfoModel.regsName": line.extra_info['regsName'],
           "busInfoModel.bj": '0.00',
           "busInfoModel.xspj": "0.00",
           "busInfoModel.ptpj": str(line.full_price)+'0'
           }

        riders = order.riders
        count = len(riders)
        tmp = {}
        for i in range(count):
            tmp = {
                "passengers[%s].idCode" % i: riders[i]["id_number"],
                "passengers[%s].cname" % i: riders[i]["name"],
                "passengers[%s].phone" % i: riders[i]["telephone"],
                "passengers[%s].insTypeCode" % i: "2",
                "passengers[%s].psgBabyFlg" % i: "0",
                "passengers[%s].psgInsuranceFlg" % i: "0",
                "passengers[%s].ticketType" % i: '1',
                "passengers[%s].insPrice" % i: "0",
                "passengers[%s].idType" % i: "1",
            }

            data.update(tmp)
        order_url = "http://60.2.147.28/com/yxd/pris/openapi/addOrder.action"
        headers = rebot.http_header()
        r = rebot.http_post(order_url, data=data, headers=headers, cookies=json.loads(rebot.cookies))
        ret = r.json()
        return ret

    def send_order_request(self, rebot, order=None, lock_info=None):
        detail_url = "http://60.2.147.28/com/yxd/pris/openapi/queryOrderByNo.action"
        headers = rebot.http_header()
        data = {
            "orderNo": order.lock_info["values"]['orderInfo']['orderMap']['ddh'] if order else lock_info["values"]['orderInfo']['orderMap']['ddh'],
        }
        r = rebot.http_post(detail_url, data=data, headers=headers, cookies=json.loads(rebot.cookies) )
        ret = r.json()
        return {
            "orderId": ret["values"]["orderInfoPreviewModel"]['order']['orderId'],
        }

    def send_orderDetail_request(self, rebot, order=None, lock_info=None):
        detail_url = "http://60.2.147.28/com/yxd/pris/openapi/orderDetail.action"
        headers = rebot.http_header()
#         rebot.login()
#         rebot.reload()
        data = {
            "orderId": order.lock_info['encode_orderId'],
        }
        r = rebot.http_post(detail_url, data=data, headers=headers, cookies=json.loads(rebot.cookies))
        ret = r.json()
        return {
            "pay_status": ret['values']['result']['order']['payState'],
            "state": ret['values']['result']['order']['orderState'],
            "order_no": ret['values']['result']['order']['orderNo'],
            "pick_no": ret['values']['result']['order']['takeTicketNo'],
            "pick_code": ret['values']['result']['order']['takfPw'],
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
        rebot = HebkyAppRebot.objects.get(telephone=order.source_account)
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
                "001001": "等待付款",
                "001002": "取消购票",
                "001003": "购票成功",
                "001004": "购票失败",
                "001005": "退票成功",
                "001006": "改签成功",
                "001007": "等待付款"
                }
        if state == "001003": #"出票成功":
            pick_no, pick_code = ret["pick_no"], ret["pick_code"]
            dx_info = {
                "time": order.drv_datetime.strftime("%Y-%m-%d %H:%M"),
                "start": order.line.s_sta_name,
                "end": order.line.d_sta_name,
                "code": pick_code,
                "no": pick_no,
            }
            dx_tmpl = DUAN_XIN_TEMPL[SOURCE_HEBKY]
            code_list = ["%s|%s" % (pick_no, pick_code)]
            msg_list = [dx_tmpl % dx_info]
            result_info.update({
                "result_code": 1,
                "result_msg": order_status_mapping[state],
                "pick_code_list": code_list,
                "pick_msg_list": msg_list,
            })

        elif state == "001007": #"出票中":
            result_info.update({
                "result_code": 4,
                "result_msg": order_status_mapping[state],
            })
        elif state in ("001002", "001004", "001005"):#取消购票,购票失败,退票成功
            result_info.update({
                "result_code": 2,
                "result_msg": order_status_mapping[state],
            })
        return result_info

    def get_pay_page(self, order, valid_code="", session=None, pay_channel="alipay" ,**kwargs):
        if not order.source_account:
            rebot = order.get_lock_rebot()
        rebot = HebkyWebRebot.objects.get(telephone=order.source_account)

        def _get_page(rebot):
            if order.status == STATUS_WAITING_ISSUE:
                rebot_app = order.get_lock_rebot()
                res = self.send_orderDetail_request(rebot_app, order)
                if res['pay_status'] == '005002':
                    return {"flag": "false", "content": '订单已经支付?'}
                order_url = "http://60.2.147.28/dync/09/wsgp/order_success.jsp?orderNo=%s"%order.raw_order_no
                headers = {
                    "User-Agent": rebot.user_agent,
                    "Content-Type": "application/x-www-form-urlencoded",
                }
                data = {}
                cookies = json.loads(rebot.cookies)
                r = requests.post(order_url, data=data, headers=headers, cookies=cookies)
                soup = BeautifulSoup(r.content, "lxml")
                payCompanyType = soup.select("#order_submit_zfslx")[0].get("value")
                cookies.update(dict(r.cookies))
                to_pay_url = "http://60.2.147.28/com/yxd/pris/wsgp/atoPayPage.action"
                data = {
                          "orderId": order.lock_info['encode_orderId'],
                          "payCompanyType": payCompanyType
                          }
                r = requests.post(to_pay_url, data=data, headers=headers, cookies=cookies)
                sel = etree.HTML(r.content)
                cookies.update(dict(r.cookies))
                payAmount = sel.xpath('//form[@id="payOrderForm"]/input[@id="payAmount"]/@value')[0]
#                 title = u"支付宝支付(PC)"
#                 paymentCompanyCode = sel.xpath('//td/img[@title="%s"]/@pcompany'%title)
#                 pay_url = "http://60.2.147.28:80/com/yxd/pris/payment/payOnline.action"
#                 params = {
#                   "orderId": order.lock_info['encode_orderId'],
#                   "paymentCompanyCode": paymentCompanyCode
#                   }
                pay_url = "http://60.2.147.28/com/hy/cpt/biz/payment/common/toPayment.action"
                params ={
                    "orderId": order.lock_info['encode_orderId'],
                    "payOrderNo": order.raw_order_no,
                    "payCompanyCode": "002",
                    "payAmount": payAmount
                    }
                r = requests.post(pay_url, data=params, headers=headers, cookies=cookies)
                order.update(pay_channel='yh')
                return {"flag": "html", "content": r.content}

        if valid_code:
            info = json.loads(session["pay_login_info"])
            headers = info["headers"]
            cookies = info["cookies"]
            custom_headers = {}
            custom_headers.update(headers)
            custom_headers.update({"Content-Type": "application/x-www-form-urlencoded"})
            url = "http://60.2.147.28//com/yxd/pris/common/personLogin.action?username=%s&password=%s&rand=%s&isChkUser=0&isAutoLogin=0"%(rebot.telephone,rebot.password,valid_code)
            r = requests.get(url, headers=custom_headers, cookies=cookies)
            cookies.update(dict(r.cookies))
            rebot.modify(cookies=json.dumps(cookies))
        is_login = rebot.test_login_status()

        if is_login:
            if order.status in (STATUS_WAITING_LOCK, STATUS_LOCK_RETRY):
                self.lock_ticket(order)
            return _get_page(rebot)
        else:
            login_form = "http://60.2.147.28/dync/09/grzx/userLogin.jsp"
            ua = random.choice(BROWSER_USER_AGENT)
            headers = {"User-Agent": ua}
            r = requests.get(login_form, headers=headers)
            soup = BeautifulSoup(r.content, "lxml")
            valid_url = soup.select("#img_val")[0].get("src")
            data = {
                "cookies": dict(r.cookies),
                "headers": headers,
                "valid_url": valid_url,
            }
            session["pay_login_info"] = json.dumps(data)
            return {"flag": "input_code", "content": ""}

    def do_refresh_line(self, line):
        result_info = {
            "result_msg": "",
            "update_attrs": {},
        }
        now = dte.now()
        ua = random.choice(MOBILE_USER_AGENG)
        headers = {"User-Agent": ua}
#         data = {
#             "startDepotCode": line.extra_info['s_code'],
#             "busCompanyCode": line.extra_info['busCompanyCode'],
#             }
#
#         url = "http://60.2.147.28/com/yxd/pris/wsgp/isInternet.action"
#         res = requests.post(url, data=data, headers=headers)
#         ret = res.json()
#         result = ret['values']['result']
#         if result == '0':
#             result_info.update(result_msg="station no internet", update_attrs={"left_tickets": 0, "refresh_datetime": now})
#             return result_info

        line_url = 'http://60.2.147.28/com/yxd/pris/openapi/queryAllTicket.action'
        data = {
            "arrivalDepotCode": line.extra_info['e_code'],
            "beginTime": line.drv_date,
            "startName": line.s_sta_name,
            "endName": line.d_city_name,
            "startDepotCode": line.extra_info['s_code']
        }
        try:
            r = requests.post(line_url, data=data, headers=headers)
            res = r.json()
        except:
            result_info.update(result_msg="timeout default 10", update_attrs={"left_tickets": 10, "refresh_datetime": now})
            return result_info
        if res["akfAjaxResult"] != "0":
            result_info.update(result_msg="error response", update_attrs={"left_tickets": 0, "refresh_datetime": now})
            return result_info

        update_attrs = {}
        for d in res["values"]["resultList"]:
            if d['stopFlag'] == '0':
                drv_datetime = dte.strptime("%s %s" % (d["departDate"], d["leaveTime"]), "%Y-%m-%d %H:%M")
                line_id_args = {
                    "s_city_name": line.s_city_name,
                    "d_city_name": line.d_city_name,
                    "bus_num": d["busCode"],
                    "crawl_source": line.crawl_source,
                    "drv_datetime": drv_datetime,
                }
                line_id = md5("%(s_city_name)s-%(d_city_name)s-%(drv_datetime)s-%(bus_num)s-%(crawl_source)s" % line_id_args)
                try:
                    obj = Line.objects.get(line_id=line_id)
                except Line.DoesNotExist:
                    continue
                info = {
                    "full_price": float(d["fullPrice"]),
                    "fee": 0,
                    "left_tickets": int(d["remainSeats"]),
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
