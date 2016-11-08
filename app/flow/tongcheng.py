#!/usr/bin/env python
# encoding: utf-8

import random
import json
import urllib
import urllib2
import datetime
import requests

from app.constants import *
from app.flow.base import Flow as BaseFlow
from app.models import Line, TCWebRebot, Order, TCAppRebot
from datetime import datetime as dte
from app.utils import md5
from bs4 import BeautifulSoup


class Flow(BaseFlow):

    name = "tongcheng"

    def do_lock_ticket_by_app(self, order):
        lock_result = {
            "lock_info": {},
            "source_account": order.source_account,
            "result_code": 0,
            "result_reason": "",
            "pay_url": "",
            "raw_order_no": "",
            "expire_datetime": "",
            "pay_money": 0,
        }
        rebot = order.get_lock_rebot(rebot_cls=TCAppRebot)
        line = order.line

        is_login = rebot.test_login_status()
        if not is_login:
            if rebot.login() == "OK":
                is_login = 1
        # 未登录
        if not is_login:
            lock_result.update({
                "result_code": 2,
                "source_account": rebot.telephone,
                "result_reason": u"账号未登录",
            })
            return lock_result

        # 构造表单参数
        riders = []
        for r in order.riders:
            riders.append({
                "name": unicode(r["name"]),
                "IDType": "1",
                "IDCard": r["id_number"],
                "passengersType": "0",
            })
        data = {
            "memberId": rebot.user_id,
            "ticketsInfo": [{
                "coachType": line.vehicle_type,
                "coachNo": line.bus_num,
                "departure": line.s_city_name,
                "destination": line.d_city_name,
                "dptStation": line.s_sta_name,
                "arrStation": line.d_sta_name,
                "dptDateTime": "%sT%s:00" % (line.drv_date, line.drv_time),
                "dptDate": line.drv_date,
                "dptTime": line.drv_time,
                "ticketPrice": line.full_price,
                "ticketFee": 0,
                "ticketLeft": str(line.left_tickets),
                "canBooking": True,
                "bookingType": 1,
                "timePeriodType": line.extra_info.get("timePeriodType", 1),
                "dptStationCode": line.s_sta_id,
                "exData2": "",
                "runTime": line.extra_info.get("runTime", ""),
                "distance": "",
                "runThrough": "",
                "AgentType": line.extra_info.get("AgentType", 7),
                "ExtraSchFlag": 0,
                "serviceChargeID": line.extra_info.get("serviceChargeID", 0),
                "serviceChargePrice": line.extra_info.get("serviceChargePrice", 0),
                "isHomeDelivery":0,
                # "$$hashKey": "09X",
                "$$hashKey": "017",
                "optionType": 1
            }],
            "contactInfo": {
                "name": order.contact_info["name"],
                "IDCard": order.contact_info["id_number"],
                "IDType": 1,
                "mobileNo": order.contact_info["telephone"],
            },
            "passengersInfo": riders,

            "totalAmount": order.order_price,
            "stationCode": line.s_sta_id,
            "AlternativeFlag":0,
            "isSubscribe":False,
            "count": order.ticket_amount,
            "coachType": line.vehicle_type,
            "activityId":0,
            "reductAmount":0,
            "reduceType":0,
            "activityType":0,
            "couponCode":"",
            "couponAmount":0,
            "insuranceId":0,
            "insuranceAmount":0,
            "voucherId":0,
            "voucherSellPrice":0,
            "serviceChargeId": line.extra_info.get("serviceChargeID", 0),
            "serviceChargeType": line.extra_info.get("serviceChargeType", 0),
            "serviceChargeAmount": line.extra_info.get("serviceChargePrice", 0)*order.ticket_amount,
            "serviceChargeUnitPrice": line.extra_info.get("serviceChargePrice", 0),
            "sessionId":"100362285"
        }
        url = "http://tcmobileapi.17usoft.com/bus/OrderHandler.ashx"
        r = rebot.http_post(url, "createbusorder", data)
        ret = r.json()["response"]
        desc = ret["header"]["rspDesc"]
        if ret["header"]["rspCode"] == "0002":
            expire_time = dte.now()+datetime.timedelta(seconds=20*60)
            lock_result.update({
                "result_code": 1,
                "result_reason": desc,
                "pay_url": "",
                "raw_order_no":  ret["body"]["orderSerialId"],
                "expire_datetime": expire_time,
                "source_account": rebot.telephone,
                "pay_money": float(ret["body"]["payAmount"]),
                "lock_info": ret["body"],
            })
        else:
            code = 0
            if u"此线路服务费不可用" in desc:
                code = 2
            if u"已暂停网售" in desc:
                self.close_line(order.line, desc)
            lock_result.update({
                "result_code": code,
                "result_reason": desc,
                "source_account": rebot.telephone,
            })
        return lock_result

    def do_lock_ticket(self, order):
        # order.line.refresh(force=1)
        if order.line.s_province in ["湖北"]:
            return self.do_lock_ticket_by_web(order)
        else:
            return self.do_lock_ticket_by_app(order)
        # line = order.line
        # if line.s_city_name in ["南通", "镇江", "无锡", "苏州"]:
        #     return self.do_lock_ticket_by_web(order)
        # else:
        #     return self.do_lock_ticket_by_app(order)


    def do_lock_ticket_by_web(self, order):
        line = order.line
        lock_result = {
            "lock_info": {},
            "source_account": order.source_account,
            "result_code": 0,
            "result_reason": "",
            "pay_url": "",
            "raw_order_no": "",
            "expire_datetime": "",
            "pay_money": 0,
        }
        #rebot = order.get_lock_rebot(rebot_cls=TCWebRebot)
        rebot = order.get_lock_rebot(rebot_cls=TCAppRebot)
        rebot = TCWebRebot.objects.get(telephone=rebot.telephone)

        is_login = rebot.test_login_status()
        if not is_login:
            if rebot.login() == "OK":
                is_login = 1
        # 未登录
        if not is_login:
            lock_result.update({
                "result_code": 2,
                "source_account": rebot.telephone,
                "result_reason": "账号未登录",
            })
            return lock_result

        # 构造表单参数
        riders = []
        for r in order.riders:
            riders.append({
                "name": unicode(r["name"]),
                "IDType": "1",
                "IDCard": r["id_number"],
                "passengersType": "1",
                "IsLinker": False,
            })
        data = {
            "MemberId": rebot.user_id,
            # "TotalAmount": line.real_price()*order.ticket_amount,
            "TotalAmount": line.full_price*order.ticket_amount,
            "InsuranceId": "",
            "InsuranceAmount": 0,
            "TicketsInfo": [
                {
                    "CoachType": line.vehicle_type,
                    "CoachNo": line.bus_num,
                    "Departure": line.s_city_name,
                    "Destination": line.d_city_name,
                    "dptStation": line.s_sta_name,
                    "ArrStation": line.d_sta_name,
                    "dptDateTime": "%sT%s:00" % (line.drv_date, line.drv_time),
                    "DptDate": line.drv_date,
                    "dptTime": line.drv_time,
                    "ticketPrice": line.full_price,
                    "OptionType": 1,

                    "agentType": 1,
                    "agentNo": 0,
                    "scheduleNo": ""
                }
            ],
            "ContactInfo": {
                "Name": order.contact_info["name"],
                "MobileNo": order.contact_info["telephone"],
                "IDType": 1,
                "IDCard": order.contact_info["id_number"],
            },
            "PassengersInfo": riders,
            "Count": order.ticket_amount,
            "StationCode": line.s_sta_id,
            "ticketFee": 0,
            #"serviceChargeId": 90 if line.s_city_name in ["南通", "镇江"] else 0,
            "serviceChargeId": line.extra_info.get("serviceChargeID", 0),
            "serviceChargeType": line.extra_info.get("serviceChargeType", 0),
            # "serviceChargeType": "1",
        }
        ret = self.send_lock_request(order, rebot, data)
        ret = ret["response"]
        desc = ret["header"]["rspDesc"]
        if ret["header"]["rspCode"] == "0000":
            expire_time = dte.now()+datetime.timedelta(seconds=20*60)
            order_no, order_id = self.query_order_no(order, rebot)
            lock_result.update({
                "result_code": 1,
                "result_reason": desc,
                "pay_url": ret["body"]["PayUrl"],
                "raw_order_no": order_no,
                "expire_datetime": expire_time,
                "source_account": rebot.telephone,
                "pay_money": float(ret["body"]["TotalFee"]),
                "lock_info": {"orderId": order_id}
            })
        else:
            if u"此线路暂不可预订,请选择其他出发站或线路" in desc or "请重新查询线路后再预订" in desc:
                lock_result.update({
                    "result_code": 2,
                    "result_reason": desc,
                    "source_account": rebot.telephone,
                })
            else:
                lock_result.update({
                    "result_code": 2,
                    "result_reason": desc,
                    "pay_url": "",
                    "raw_order_no": "",
                    "expire_datetime": None,
                    "source_account": rebot.telephone,
                })
        return lock_result

    def send_lock_request(self, order, rebot, data):
        """
        单纯向源站发请求
        """
        submit_url = "http://bus.ly.com/Order/CreateBusOrder"
        headers = {
            "User-Agent": rebot.user_agent,
            "Content-Type": "application/json",
        }
        cookies = json.loads(rebot.cookies)
        resp = rebot.http_post(submit_url,
                             data=json.dumps(data),
                             headers=headers,
                             cookies=cookies,
                             )
        ret = resp.json()
        return ret

    def query_order_no(self, order, rebot):
        """
        去源站拿订单号
        """
        url = "http://member.ly.com/ajaxhandler/OrderListHandler.ashx?OrderFilter=1&ProjectTag=0&DateType=2&PageIndex=1"
        headers = {"User-Agent": rebot.user_agent}
        cookies = json.loads(rebot.cookies)
        r = rebot.http_get(url, headers=headers, cookies=cookies)
        res = r.json()
        line = order.line
        for info in res["ReturnValue"]["OrderDetailList"]:
            order_no = info["SerialId"]
            bus_num = info["CoachNo"]
            if bus_num != line.bus_num:
                continue

            # 该订单已经有主了
            if Order.objects.filter(crawl_source=order.crawl_source, raw_order_no=order_no):
                continue

            detail = self.send_order_request_web(rebot, order_no)
            if detail["drv_datetime"] != order.drv_datetime:
                continue
            if detail["contact_name"] != order.contact_info["name"]:
                continue
            if detail["contact_phone"] != order.contact_info["telephone"]:
                continue
            return order_no, detail["order_id"]
        return "", ""


    def send_order_request_web(self, rebot, raw_order_no):
        detail_url = "http://member.ly.com/bus/order/orderDetail?id=%s" % raw_order_no
        headers = {
            "User-Agent": rebot.user_agent,
        }
        cookies = json.loads(rebot.cookies)
        r = rebot.http_get(detail_url, headers=headers, cookies=cookies)
        soup = BeautifulSoup(r.content, "lxml")
        state = soup.select(".paystate")[0].get_text().strip()
        sdate = soup.select(".list01_info table")[0].findAll("tr")[2].get_text().strip()
        drv_datetime = dte.strptime(sdate, "%Y-%m-%d %H:%M:%S")
        contact_lst = soup.select(".list01_info table")[3].select("td")
        contact_name = contact_lst[0].get_text().lstrip("姓名：").strip()
        contact_phone = contact_lst[1].get_text().lstrip("手机：").strip()
        order_id = soup.select_one("#payArg").get("value").split(",")[0]

        return {
            "state": state,
            "drv_datetime": drv_datetime,
            "contact_name": contact_name,
            "contact_phone": contact_phone,
            "order_id": order_id,
        }

    def send_order_request_by_app(self, order):
        rebot = TCAppRebot.objects.get(telephone=order.source_account)
        data = {
            "memberid": rebot.user_id,
            "orderId": order.lock_info["orderId"],
        }
        url = "http://tcmobileapi.17usoft.com/bus/OrderHandler.ashx"
        r = rebot.http_post(url, "getbusorderdetail", data)
        return r.json()["response"]

    def do_refresh_issue_by_app(self, order):
        result_info = {
            "result_code": 0,
            "result_msg": "",
            "pick_code_list": [],
            "pick_msg_list": [],
        }
        if not self.need_refresh_issue(order):
            result_info.update(result_msg="状态未变化")
            return result_info
        ret = self.send_order_request_by_app(order)
        desc = ret["header"]["rspDesc"]
        if ret["header"]["rspCode"] != "0000":
            result_info.update(result_msg=desc)
            return result_info
        state = ret["body"]["orderStateName"]
        if state == "出票中":
            result_info.update({
                "result_code": 4,
                "result_msg": state,
            })
        # elif state == "已取消":  # 已取消也有可能已经支付了, 避免造成损失, 先注销掉
        #     result_info.update({
        #         "result_code": 5,
        #         "result_msg": state,
        #     })
        elif state=="出票成功":
            body = ret["body"]
            result_info.update({
                "result_code": 1,
                "result_msg": state,
                "pick_code_list": ["%s|%s" % (body["getTicketNo"], body["getTicketPassWord"])],
                "pick_msg_list": [body["getTicketInfo"]],
            })
        elif state == "已退款":
            result_info.update({
                "result_code": 3,
                "result_msg": state,
            })
        elif state=="出票失败":
            self.close_line(order.line, "出票失败")
            result_info.update({
                "result_code": 2,
                "result_msg": state,
            })
        return result_info

    def do_refresh_issue(self, order):
        return self.do_refresh_issue_by_app(order)
        # result_info = {
        #     "result_code": 0,
        #     "result_msg": "",
        #     "pick_code_list": [],
        #     "pick_msg_list": [],
        # }
        # if not self.need_refresh_issue(order):
        #     result_info.update(result_msg="状态未变化")
        #     return result_info
        # rebot = TCWebRebot.objects.get(telephone=order.source_account)
        # if not order.raw_order_no:
        #     order.modify(raw_order_no=self.query_order_no(order, rebot))
        # if not order.raw_order_no:
        #     result_info.update(result_msg="状态未变化, 没拿到源站订单号")
        #     return result_info
        # ret = self.send_order_request(rebot, order.raw_order_no)
        # state = ret["state"]
        # if state == "出票中":
        #     result_info.update({
        #         "result_code": 4,
        #         "result_msg": state,
        #     })
        # # elif state == "已取消":  # 已取消也有可能已经支付了, 避免造成损失, 先注销掉
        # #     result_info.update({
        # #         "result_code": 2,
        # #         "result_msg": state,
        # #     })
        # elif state=="出票失败":
        #     self.close_line(order.line, "出票失败")
        #     result_info.update({
        #         "result_code": 2,
        #         "result_msg": state,
        #     })
        # elif state=="出票成功":
        #     result_info.update({
        #         "result_code": 1,
        #         "result_msg": state,
        #         "pick_code_list": [],
        #         "pick_msg_list": [],
        #     })
        # return result_info

    def get_pay_page(self, order, valid_code="", session=None, pay_channel="alipay" ,**kwargs):
        if not order.source_account:
            rebot = order.get_lock_rebot()
        rebot = TCWebRebot.objects.get(telephone=order.source_account)
        if valid_code:
            info = json.loads(session["pay_login_info"])
            headers = info["headers"]
            cookies = info["cookies"]
            rebot.login(headers=headers, cookies=cookies, valid_code=valid_code)

        is_login = rebot.test_login_status()
        if is_login:
            if order.status in [STATUS_LOCK_RETRY, STATUS_WAITING_LOCK]:
                self.lock_ticket(order)
            if order.status == STATUS_WAITING_ISSUE:
                headers = {
                    "User-Agent": rebot.user_agent,
                    "Content-Type": "application/x-www-form-urlencoded",
                }
                form_str = "OrderId=%s&TotalAmount=%s" % (order.lock_info["orderId"], order.pay_money)
                r = rebot.http_post("http://member.ly.com/bus/Pay/MobileGateway",
                                     data=form_str,
                                     headers=headers,
                                     cookies=json.loads(rebot.cookies))
                try:
                    res = r.json()["response"]
                except Exception, e:
                    rebot.modify(ip="")
                    raise e
                if res["header"]["rspCode"] == "0000":
                    pay_url = res["body"]["PayUrl"]
                    # return {"flag": "url", "content": pay_url}

                    r = rebot.http_get(pay_url, headers=headers, verify=False)
                    content = r.content
                    soup = BeautifulSoup(content, "lxml")
                    sign = soup.select("#aliPay")[0].get("data-sign")
                    partner = soup.find("input", attrs={"name": "partner"}).get("value")
                    serial = soup.find("input", attrs={"name": "serial"}).get("value")
                    pay_type = soup.select("#aliPay")[0].get("data-value")
                    params = {
                        "sign": sign,
                        "partner": partner,
                        "serial": serial,
                        "pay_data": pay_type,
                    }
                    alipay_url = "https://pay.ly.com/pc/payment/GatewayPay"
                    form_str = urllib.urlencode(params)
                    r = rebot.http_post(alipay_url, headers=headers, data=form_str, verify=False)
                    res = r.json()

                    web_url = res["web_url"]
                    parser = urllib2.urlparse.urlparse(web_url)
                    data = {}
                    for s in parser.query.split("&"):
                        n, v = s.split("=")
                        data[n] = v
                    pay_money = float(data["total_fee"])
                    trade_no = data["out_trade_no"]
                    if order.pay_money != pay_money or order.pay_order_no != trade_no:
                        order.modify(pay_money=pay_money, pay_order_no=trade_no,pay_channel='alipay')
                    return {"flag": "url", "content": web_url}
                return {"flag": "html", "content": r.content}
        else:
            login_form = "https://passport.ly.com"
            valid_url = "https://passport.ly.com/AjaxHandler/ValidCode.ashx?action=getcheckcode&name=%s" % rebot.telephone
            headers = {"User-Agent": random.choice(BROWSER_USER_AGENT)}
            r = rebot.http_get(login_form, headers=headers, verify=False)
            data = {
                "cookies": dict(r.cookies),
                "headers": headers,
                "valid_url": valid_url,
            }
            session["pay_login_info"] = json.dumps(data)
            return {"flag": "input_code", "content": ""}

    def do_refresh_line(self, line):
        return self.do_refresh_line_by_app(line)

        # result_info = {
        #     "result_msg": "",
        #     "update_attrs": {},
        # }
        # line_url = "http://m.ly.com/bus/BusJson/BusSchedule"
        # params = dict(
        #     Departure=line.s_city_name,
        #     Destination=line.d_city_name,
        #     DepartureDate=line.drv_date,
        #     DepartureStation="",
        #     DptTimeSpan=0,
        #     HasCategory="true",
        #     Category="0",
        #     SubCategory="",
        #     ExParms="",
        #     Page="1",
        #     PageSize="1025",
        #     BookingType="0"
        # )
        # headers = {
        #     "User-Agent": random.choice(BROWSER_USER_AGENT),
        #     "Content-Type": "application/x-www-form-urlencoded",
        # }
        # r = requests.post(line_url, data=urllib.urlencode(params), headers=headers)
        # res = r.json()
        # res = res["response"]
        # now = dte.now()
        # if res["header"]["rspCode"] != "0000":
        #     result_info.update(result_msg="error response", update_attrs={"left_tickets": 0, "refresh_datetime": now})
        #     return result_info

        # update_attrs = {}
        # for d in res["body"]["schedule"]:
        #     drv_datetime = dte.strptime("%s %s" % (d["dptDate"], d["dptTime"]), "%Y-%m-%d %H:%M")
        #     line_id_args = {
        #         "s_city_name": line.s_city_name,
        #         "d_city_name": line.d_city_name,
        #         #"bus_num": d["coachNo"],
        #         "s_sta_name": d["dptStation"],
        #         "d_sta_name": d["arrStation"],
        #         "crawl_source": line.crawl_source,
        #         "drv_datetime": drv_datetime,
        #     }
        #     line_id = md5("%(s_city_name)s-%(d_city_name)s-%(drv_datetime)s-%(s_sta_name)s-%(d_sta_name)s-%(crawl_source)s" % line_id_args)
        #     try:
        #         obj = Line.objects.get(line_id=line_id)
        #     except Line.DoesNotExist:
        #         continue
        #     info = {
        #         "full_price": float(d["ticketPrice"]),
        #         "fee": 0,
        #         "left_tickets": int(d["ticketLeft"]),
        #         "refresh_datetime": now,
        #         "extra_info": {},
        #     }
        #     if line_id == line.line_id:
        #         update_attrs = info
        #     else:
        #         obj.update(**info)
        # if not update_attrs:
        #     result_info.update(result_msg="no line info", update_attrs={"left_tickets": 0, "refresh_datetime": now})
        # else:
        #     result_info.update(result_msg="ok", update_attrs=update_attrs)
        # return result_info

    def do_refresh_line_by_app(self, line):
        now = dte.now()
        result_info = {
            "result_msg": "",
            "update_attrs": {},
        }
        url = "http://tcmobileapi.17usoft.com/bus/QueryHandler.ashx"
        rebot = TCAppRebot.get_one()
        data = {
            "departure": line.s_city_name,
            "destination": line.d_city_name,
            "dptDate": line.drv_date,
            "queryType": 1,
            "subCategory": 0,
            "page": 1,
            "pageSize": 1025,
            "hasCategory": 1,
            "dptStation": "",
            "arrStation": "",
            "dptTimeSpan": 0
        }
        try:
            r = rebot.http_post(url, "getbusschedule", data)
        except Exception, e:
            result_info.update(result_msg="exception_ok", update_attrs={"left_tickets": 2, "refresh_datetime": now})
            return result_info
        res = r.json()
        res = res["response"]
        if res["header"]["rspCode"] != "0000" or not res["body"]:
            result_info.update(result_msg="error response", update_attrs={"left_tickets": 0, "refresh_datetime": now})
            return result_info

        update_attrs = {}
        for d in res["body"]["schedule"]:
            # if not d["coachNo"]:
            #     continue
            if d["canBooking"]:
                left = max(int(d["ticketLeft"]), 0) or 15
            else:
                left = 0
            drv_datetime = dte.strptime("%s %s" % (d["dptDate"], d["dptTime"]), "%Y-%m-%d %H:%M")
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

            info = {
                "full_price": float(d["ticketPrice"]),
                "fee": float(d["serviceChargePrice"]),
                "left_tickets": left,
                "refresh_datetime": now,
                "extra_info": {
                    "AgentType":d["AgentType"],
                    "timePeriodType":d[u'timePeriodType'],
                    "serviceChargeID": d["serviceChargeID"],
                    "serviceChargePrice": d["serviceChargePrice"],
                    "serviceChargeType": d.get("serviceChargeType", 0),
                    "runTime": d["runTime"]
                },
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
