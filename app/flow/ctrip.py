# -*- coding:utf-8 -*-
import random
import requests
import datetime
import json
import urllib

from app.constants import *
from app.flow.base import Flow as BaseFlow
from app.models import CTripRebot
from datetime import datetime as dte
from app.utils import idcard_birthday
from app import order_log

class Flow(BaseFlow):

    name = "ctrip"

    def do_lock_ticket(self, order):
        with CTripRebot.get_and_lock(order) as rebot:
            line = order.line
            data = {
                "head": rebot.head,
                "fromCityName": line.starting.city_name,
                "toCityName": line.destination.city_name,
                "fromStationName": line.starting.station_name,
                "toStationName": line.destination.station_name,
                "ticketDate": line.drv_date,
                "ticketTime": line.drv_time,
                "busNumber": line.bus_num,
                "busType": line.vehicle_type,
                "toTime": "",
                "toDays": 0,
                "contactMobile": order.contact_info["telephone"],
                "ticket_type": "成人票",
                "acceptFreeInsurance": True,
                "selectServicePackage2": "0",
                "clientType": "Android--h5",
                "identityInfoCount": len(order.riders),
                "isJoinActivity": 0,
                "selectOffsetActivityType": 0,
                "couponCode": "",
                "useCouponClientType": 2,
                "acceptFromDateFloating": False,
                "productPackageId": 0,
                "DispatchType": 0,
                "contactName": order.contact_info["name"],
                "contactPaperType": "身份证",
                "contactPaperNum": order.contact_info["id_number"],
                "contentType": "json"
            }
            for i, r in enumerate(order.riders):
                idcard = r["id_number"]
                birthday = idcard_birthday(idcard).strftime("%Y-%m-%d")
                data.update({"identityInfo%d" % (i+1): "%s;身份证;%s;%s" % (r["name"], idcard, birthday)})
            ret = self.send_lock_request(rebot, data)

            lock_result = {
                "lock_info": ret,
                "source_account": rebot.telephone,
            }
            if ret["code"] == 1:
                raw_order = ret["return"]["orderNumber"]
                expire_time = dte.now()+datetime.timedelta(seconds=60*60)
                total_price = ret["return"]["displayRealPayFee"]
                lock_result.update({
                    "result_code": 1,
                    "result_reason": "",
                    "pay_url": "",
                    "raw_order_no": raw_order,
                    "expire_datetime": expire_time,
                    "pay_money": total_price,
                })
            else:
                lock_result.update({
                    "result_code": 0,
                    "result_reason": ret["message"],
                    "pay_url": "",
                    "raw_order_no": "",
                    "expire_datetime": None,
                })
            return lock_result

    def send_lock_request(self, rebot, data):
        """
        单纯向源站发请求
        """
        url = "https://sec-m.ctrip.com/restapi/busphp/app/index.php?param=/api/home&method=order.addOrder&v=1.0&ref=ctrip.h5&partner=ctrip.h5&clientType=Android--h5&_fxpcqlniredt=09031120210146050165"
        headers = {
            "User-Agent": rebot.user_agent,
            "Content-type": "application/json; charset=UTF-8",
        }
        r = requests.post(url, data=json.dumps(data), headers=headers, timeout=20)
        return r.json()

    def do_refresh_issue(self, order):
        result_info = {
            "result_code": 0,
            "result_msg": "",
            "pick_code_list": [],
            "pick_msg_list": [],
        }
        if order.status not in [STATUS_WAITING_ISSUE, STATUS_ISSUE_ING]:
            result_info.update(result_msg="状态未变化")
            return result_info

        rebot = CTripRebot.objects.get(telephone=order.source_account)
        ret = self.send_order_request(order, rebot)

        detail = ret["return"]
        code_list, msg_list = [], []
        status = detail["orderState"]
        if status == "已成交":
            pick_info = detail["fetcherInfo"]
            for d in pick_info:
                if d["k"] == "取票密码":
                    code = d["v"]
                    code_list.append(code)
                    dx_tmpl = DUAN_XIN_TEMPL[SOURCE_CTRIP]
                    dx_info = {
                        "time": order.drv_datetime.strftime("%Y-%m-%d %H:%M"),
                        "start": order.line.starting.station_name,
                        "end": order.line.destination.station_name,
                        "amount": order.ticket_amount,
                        "code": code,
                    }
                    msg_list.append(dx_tmpl % dx_info)
                    break
            result_info.update({
                "result_code": 1,
                "result_msg": status,
                "pick_code_list": code_list,
                "pick_msg_list": msg_list,
            })
        elif status in ["超时未支付", "已取消"]:
            result_info.update({
                "result_code": 2,
                "result_msg": status,
            })
        elif status in ["全部退款", "退款中"]:
            result_info.update({
                "result_code": 3,
                "result_msg": status,
            })
        elif status == "购票中":
            result_info.update({
                "result_code": 4,
                "result_msg": status,
            })
        return result_info

    def send_order_request(self, order, rebot):
        data = {
            "head": rebot.head,
            "orderNumber": order.raw_order_no,
            "contentType": "json"
        }
        url = "http://m.ctrip.com/restapi/busphp/app/index.php?param=/api/home&method=order.detail&v=1.0&ref=ctrip.h5&partner=ctrip.h5&clientType=Android--h5&_fxpcqlniredt=09031120210146050165"
        headers = {
            "User-Agent": rebot.user_agent,
            "Content-type": "application/json; charset=UTF-8",
        }
        r = requests.post(url, data=json.dumps(data), headers=headers, timeout=20)
        ret = r.json()
        return ret

    def do_refresh_line(self, line):
        result_info = {
            "result_msg": "",
            "update_attrs": {},
        }
        params = dict(
            param="/api/home",
            method="product.getBusDetail",
            v="1.0",
            ref="ctrip.h5",
            partner="ctrip.h5",
            clientType="Android--hybrid",
            fromCity=line.starting.city_name,
            toCity=line.destination.city_name,
            busNumber=line.bus_num,
            fromStation=line.starting.station_name,
            toStation=line.destination.station_name,
            fromDate=line.drv_date,
            fromTime=line.drv_time,
            contentType="json",
        )
        base_url = "http://m.ctrip.com/restapi/busphp/app/index.php"
        url = "%s?%s" % (base_url, urllib.urlencode(params))
        ua = random.choice(MOBILE_USER_AGENG)
        r = requests.get(url, headers={"User-Agent": ua})
        ret = r.json()
        now = dte.now()
        if ret["code"] == 1:
            info = ret["return"]
            if info:
                ticket_info = info["showTicketInfo"]
                if ticket_info == "有票":
                    left_tickets = 45
                elif ticket_info.endswith("张"):
                    left_tickets = int(ticket_info[:-1])
                elif ticket_info == "预约购票":
                    left_tickets = 0
                service_info = info["servicePackage"]
                fee = 0
                for d in service_info:
                    if d["type"] == "service":
                        fee = d["amount"]
                        break
                info = {
                    "full_price": info["fullPrice"],
                    "fee": fee,
                    "left_tickets": left_tickets,
                    "refresh_datetime": now,
                }
                result_info.update(result_msg="ok", update_attrs=info)
            else:  # 线路信息没查到
                result_info.update(result_msg="no line info", update_attrs={"left_tickets": 0, "refresh_datetime": now})
        else:
            result_info.update(result_msg="fail", update_attrs={"left_tickets": 0, "refresh_datetime": now})
        return result_info

    def get_pay_page(self, order, **kwargs):
        self.refresh_issue(order)
        if order.status != STATUS_WAITING_ISSUE:
            return {"flag": "refuse", "content": ""}
        rebot = CTripRebot.objects.get(telephone=order.source_account)
        headers = {
            'User-Agent': "Mozilla/5.0 (Windows NT 6.2) AppleWebKit/536.3  (KHTML, like Gecko) Chrome/19.0.1061.0 Safari/536.3",
            "Content-Type": "application/json;charset=utf-8",
        }
        param_url = "http://m.ctrip.com/restapi/soa2/10098/HandleOrderPayment.json?_fxpcqlniredt=09031108210147109160"
        req_args = {
            "ClientVersion": "6.12",
            "Channel": "H5",
            "PaymentOrderInfos": [
                {
                    "BizType": "QiChe",
                    "OrderIDs": [order.raw_order_no,]
                }
            ],
            "From": "http://m.ctrip.com/webapp/myctrip/orders/allorders?from=%2Fwebapp%2Fmyctrip%2Findex",
            "Platform": "H5",
            "head": rebot.head,
            "contentType": "json"
        }
        r = requests.post(param_url, data=json.dumps(req_args), headers=headers)
        ret = r.json()
        order_log.info("[pay-request1] order:%s ret: %s", order.order_no, str(ret))
        if ret["Result"]["ResultCode"] == -1:
            order_log.error("[pay-fail] order:%s msg: %s", order.order_no, ret["Result"]["ResultMsg"])
        token_info = json.loads(ret["PaymentInfos"][0]["Token"])
        bus_type = token_info["bustype"]
        req_id = token_info["requestid"]
        price = token_info["amount"]
        title = token_info["title"]

        submit_url = "https://gateway.secure.ctrip.com/restful/soa2/10289/paymentinfo/submitv3?_fxpcqlniredt=09031108210147109160"
        submit_args = {
            "opttype": 1,
            "paytype": 4,
            "thirdpartyinfo": {
                "paymentwayid": "EB_MobileAlipay",
                "typeid": 0,
                "subtypeid": 4,
                "typecode": "",
                "thirdcardnum": "",
                "amount": str(price),
                "brandid": "EB_MobileAlipay",
                "brandtype": "2",
                "channelid": "109"
            },
            "opadbitmp": 4,
            "ver": 612,
            "plat": 5,
            "requestid": req_id,
            "clientextend": "eyJpc1JlYWxUaW1lUGF5IjoxLCJpc0F1dG9BcHBseUJpbGwiOjF9",
            "clienttoken": "eyAib2lkIjogIjE2NjIxMzA3NjUiLCAiYnVzdHlwZSI6ICIxNCIsICJzYmFjayI6ICJodHRwOi8vbS5jdHJpcC5jb20vd2ViYXBwL3RyYWluL2luZGV4Lmh0bWwjYnVzcmVzdWx0IiwgInRpdGxlIjogIui+vuW3ni3ph43luoYiLCAiYW1vdW50IjogIjQ3IiwgInJiYWNrIjogIiIsICJlYmFjayI6ICJodHRwOi8vbS5jdHJpcC5jb20vd2ViYXBwL3RyYWluL2luZGV4Lmh0bWwjYnVzcmVzdWx0IiwgInJlcXVlc3RpZCI6ICIxMzE1MTIzMTEwMDAwMTI5ODIzIiwgImF1dGgiOiAiNzI3NTI4ODU5RjA2MEIzMkMzMTIyMkYwMzVCNDA1NTZFN0Q1QjU2MTg4MzU3QTM1NTIxMDFDMjY3RUM3RTNCMyIsICJmcm9tIjogImh0dHA6Ly9tLmN0cmlwLmNvbS93ZWJhcHAvbXljdHJpcC9pbmRleCIsICJpc2xvZ2luIjogIjAiIH0=",
            "clientsign": "",
            "bustype": bus_type,
            "usetype": 1,
            "subusetype": 0,
            "subpay": 0,
            "forcardfee": 0,
            "forcardcharg": 0,
            "stype": 0,
            "payrestrict": {},
            "oinfo": {
                "oid": order.raw_order_no,
                "oidex": order.raw_order_no,
                "odesc": title,
                "currency": "CNY",
                "oamount": str(price),
                "displayCurrency": "CNY",
                "displayAmount": "",
                "extno": "",
                "autoalybil": True,
                "recall": ""
            },
            "cardinfo": None,
            "statistic": None,
            "cashinfo": None,
            "head": rebot.head,
            "contentType": "json"
        }
        r = requests.post(submit_url, data=json.dumps(submit_args), headers=headers)
        ret = r.json()
        pay_url = ret["thirdpartyinfo"]["sig"]
        base_url, query_str = pay_url.split("?")
        params = {}
        lst = []
        for s in query_str.split("&"):
            k, v = s.split("=")
            if k == "ctu_info":
                v = "\"{isAccountDeposit:false,isCertificate:true}\""
            params[k] = v[1:-1]
            lst.append("%s=%s" % (k, v[1:-1]))
        pay_url = "%s?%s" % (base_url, "&".join(lst))
        return {
            "flag": "url",
            "content": pay_url,
        }
