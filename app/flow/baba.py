#!/usr/bin/env python
# encoding: utf-8

import random
import requests
import json
import urllib
import datetime

from app.constants import *
from app.flow.base import Flow as BaseFlow
from app.models import Line, BabaWebRebot
from datetime import datetime as dte
from app.utils import md5
from bs4 import BeautifulSoup


class Flow(BaseFlow):

    name = "baba"

    def do_lock_ticket(self, order):
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
        with BabaWebRebot.get_and_lock(order) as rebot:
            line = order.line
            form_url = "http://www.bababus.com/baba/order/writeorder.htm"
            params = {
                "sbId": line.extra_info["sbId"],
                "stId": line.extra_info["stId"],
                "depotId": line.extra_info["depotId"],
                "busId": line.bus_num,
                "leaveDate": line.drv_date,
                "beginStationId": line.s_sta_id,
                "endStationId": line.d_sta_id,
                "endStationName": line.d_sta_name,
            }
            cookies = json.loads(rebot.cookies)
            r = requests.get("%s?%s" %(form_url,urllib.urlencode(params)),
                             headers={"User-Agent": rebot.user_agent},
                             cookies=cookies)

            # 未登录
            if not rebot.check_login_by_resp(r):
                lock_result.update({
                    "result_code": 2,
                    "source_account": rebot.telephone,
                    "result_reason": "账号未登录",
                })
                return lock_result

            soup = BeautifulSoup(r.content, "lxml")
            wrong_info = soup.select(".wrong_body .wrong_inf")
            # 订单填写页获取错误
            if wrong_info:
                inf = wrong_info[0].get_text()
                tip = soup.select(".wrong_body .wrong_tip")[1].get_text()
                lock_result.update({
                    "result_code": 2,
                    "source_account": rebot.telephone,
                    "result_reason": "%s %s" % (inf, tip),
                })
                return lock_result

            # 构造表单参数
            raw_form = {}
            for obj in soup.find_all("input"):
                name, val = obj.get("name"), obj.get("value")
                if name in ["None", "none", '']:
                    continue
                raw_form[name] = val

            submit_data = {
                "p": raw_form["p"],
                "sbId": raw_form["sbId"],
                "stId": raw_form["stId"],
                "busId": raw_form["busId"],
                "beginStationName": line.s_sta_name,
                "endStationName": line.d_sta_name,
                "leaveDate": line.drv_date,
                "leaveTime": line.drv_time,
                "routeName": raw_form["routeName"],
                "vehicleMode": raw_form["vehicleMode"],
                "busType": raw_form["busType"],
                "mileage": raw_form["mileage"],
                "fullPrice": raw_form["fullPrice"],
                "halfPrice": raw_form["halfPrice"],
                "remainSeat": raw_form["remainSeat"],
                "endStationId": raw_form["endStationId"],
                "depotId": raw_form["depotId"],
                "beginStationId": raw_form["beginStationId"],
                "contactName": order.contact_info["name"],
                "contactIdType": "1101",
                "contactIdCode": order.contact_info["id_number"],
                "contactPhone": order.contact_info["telephone"],
                "contactEmail": "",
            }
            encode_list= [urllib.urlencode(submit_data),]
            for r in order.riders:
                d = {
                    "psgName": r["name"],
                    "psgIdType": "1101",
                    "psgIdCode": r["id_number"],
                    "psgTicketType": 1,
                    "psgBabyFlg": 0,
                    "psgInsuranceTypeId": "",       # 保险
                    "saveToName": "on",
                    "isSave":1,
                }
                encode_list.append(urllib.urlencode(d))
            encode_str = "&".join(encode_list)
            ret = self.send_lock_request(order, rebot, encode_str)
            if ret["success"]:
                expire_time = dte.now()+datetime.timedelta(seconds=15*60)
                lock_result.update({
                    "result_code": 1,
                    "result_reason": ret["msgType"],
                    "pay_url": "",
                    "raw_order_no": ret["billNo"],
                    "expire_datetime": expire_time,
                    "source_account": rebot.telephone,
                })
            else:
                lock_result.update({
                    "result_code": 0,
                    "result_reason": ret["msgType"],
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
        submit_url = "http://www.bababus.com//baba/order/createorder.htm"
        headers = {
            "User-Agent": rebot.user_agent,
            "Content-Type": "application/x-www-form-urlencoded",
        }
        cookies = json.loads(rebot.cookies)
        resp = requests.post(submit_url, data=data, headers=headers, cookies=cookies)
        ret = resp.json()
        return ret

    def send_order_request(self, rebot, order):
        detail_url = "http://www.bababus.com/baba/order/detail.htm?billNo=%s" % order.raw_order_no
        headers = {
            "User-Agent": rebot.user_agent,
        }
        cookies = json.loads(rebot.cookies)
        r = requests.get(detail_url, headers=headers, cookies=cookies)
        soup = BeautifulSoup(r.content, "lxml")
        no, code ,site = "", "", ""
        for tag in soup.select(".details_taketicket .details_passenger_num"):
            s = tag.get_text().strip()
            if s.startswith("取票号:"):
                no = s.lstrip("取票号:")
            elif s.startswith("取票密码:"):
                code = s.lstrip("取票密码:")
            elif s.startswith("取票地点:"):
                site = s.lstrip("取票地点:")
        return {
            "state": soup.select(".pay_success")[0].get_text().split(u"：")[1].strip(),
            "pick_no": no,
            "pick_code": code,
            "pick_site": site,
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
        rebot = BabaWebRebot.objects.get(telephone=order.source_account)
        ret = self.send_order_request(rebot, order=order)
        state = ret["state"]
        if state == "支付超时作废":
            result_info.update({
                "result_code": 2,
                "result_msg": state,
            })
        elif state == "已作废":
            result_info.update({
                "result_code": 2,
                "result_msg": state,
            })
        elif state=="购票中":
            result_info.update({
                "result_code": 4,
                "result_msg": state,
            })
        elif state=="购票成功":
            no, code, site = ret["pick_no"], ret["pick_code"], ret["pick_site"]
            dx_info = {
                "time": order.drv_datetime.strftime("%Y-%m-%d %H:%M"),
                "start": order.line.s_sta_name,
                "end": order.line.d_sta_name,
                "code": code,
                "no": no,
                "site": site,
            }
            dx_tmpl = DUAN_XIN_TEMPL[SOURCE_BABA]
            code_list = ["%s|%s" % (no, code)]
            msg_list = [dx_tmpl % dx_info]
            result_info.update({
                "result_code": 1,
                "result_msg": state,
                "pick_code_list": code_list,
                "pick_msg_list": msg_list,
            })
        return result_info

    def get_pay_page(self, order, valid_code="", session=None, pay_channel="alipay" ,**kwargs):
        rebot = BabaWebRebot.objects.get(telephone=order.source_account)

        def _get_page(rebot):
            if order.status == STATUS_WAITING_ISSUE:
                pay_url = "http://www.bababus.com/baba/order/bankpay.htm"
                headers = {
                    "User-Agent": rebot.user_agent,
                    "Content-Type": "application/x-www-form-urlencoded",
                }
                params = {
                    "userCouponId": "",
                    "bankId": 1402,
                    "billNo": order.raw_order_no,
                }
                cookies = json.loads(rebot.cookies)
                r = requests.post(pay_url, data=urllib.urlencode(params), headers=headers, cookies=cookies)
                return {"flag": "html", "content": r.content}

        if valid_code:
            info = json.loads(session["pay_login_info"])
            headers = info["headers"]
            cookies = info["cookies"]
            params = {
                "returnurl": "",
                "userCode": rebot.telephone,
                "password": rebot.password,
                "checkCode": valid_code,
                "rememberMe": "yes",
            }
            custom_headers = {}
            custom_headers.update(headers)
            custom_headers.update({"Content-Type": "application/x-www-form-urlencoded"})
            r = requests.post("http://www.bababus.com/baba/login.htm",
                              data=urllib.urlencode(params),
                              headers=custom_headers,
                              allow_redirects=False,
                              cookies=cookies)
            cookies.update(dict(r.cookies))
            rebot.modify(cookies=json.dumps(cookies))
        is_login = rebot.test_login_status()

        if is_login:
            if order.status == STATUS_LOCK_RETRY:
                from app.flow import get_flow
                flow = get_flow(order.crawl_source)
                flow.lock_ticket(order)
            return _get_page(rebot)
        else:
            login_form = "http://www.bababus.com/baba/login.htm"
            ua = random.choice(BROWSER_USER_AGENT)
            headers = {"User-Agent": ua}
            r = requests.get(login_form, headers=headers)
            soup = BeautifulSoup(r.content, "lxml")
            valid_url = soup.select("#cc")[0].get("src")
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
        line_url = "http://s4mdata.bababus.com:80/app/v3/ticket/busList.htm"
        params = {
            "content":{
                "pageSize": 1025,
                "beginCityName": line.s_city_name,
                "currentPage": 1,
                "endCityName": line.d_city_name,
                "leaveDate": line.drv_date,
            },
            "common": {
                "pushToken": "864895020513527",
                "channelVer": "BabaBus",
                "usId": "",
                "appId": "com.hundsun.InternetSaleTicket",
                "appVer": "1.0.0",
                "loginStatus": "0",
                "imei": "864895020513527",
                "mobileVer": "4.4.4",
                "terminalType": "1"
            },
            "key": ""
        }
        ua = random.choice(MOBILE_USER_AGENG)
        headers = {"User-Agent": ua}
        r = requests.post(line_url, data=json.dumps(params), headers=headers)
        res = r.json()
        now = dte.now()
        if res["returnNo"] != "0000":
            result_info.update(result_msg="error response", update_attrs={"left_tickets": 0, "refresh_datetime": now})
            return result_info

        line_id_args = {
            "s_city_name": line.s_city_name,
            "d_city_name": line.d_city_name,
            "bus_num": line.bus_num,
            "crawl_source": line.crawl_source,
        }
        update_attrs = {}
        for d in res["content"]["busList"]:
            drv_datetime = dte.strptime("%s %s" % (d["leaveDate"], d["leaveTime"]), "%Y-%m-%d %H:%M")
            line_id_args.update(drv_datetime=drv_datetime)
            line_id = md5("%(s_city_name)s-%(d_city_name)s-%(drv_datetime)s-%(bus_num)s-%(crawl_source)s" % line_id_args)
            try:
                obj = Line.objects.get(line_id=line_id)
            except Line.DoesNotExist:
                continue
            extra_info = {"depotName": d["depotName"], "sbId": d["sbId"], "stId": d["stId"], "depotId": d["depotId"]}
            info = {
                "full_price": float(d["fullPrice"]),
                "fee": 0,
                "left_tickets": int(d["remainCount"]),
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