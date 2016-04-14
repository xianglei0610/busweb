#!/usr/bin/env python
# encoding: utf-8

import random
import requests
import json
import urllib
import datetime
import traceback
import re

from app.constants import *
from app.flow.base import Flow as BaseFlow
from app.models import Line, BabaWebRebot
from datetime import datetime as dte
from app.utils import md5
from bs4 import BeautifulSoup
from tasks import async_send_email
from app import line_log


class Flow(BaseFlow):

    name = "baba"

    #def check_rider_idcard(self, order):
    #    valid_url = "http://www.bababus.com/order/validateCard.htm"
    # psgIdCode=350628199012101520&psgIdType=1
    #    for r in order.riders:
    #        pass

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
            params = {
                "startPlace":line.s_city_name,
                "endPlace": line.d_city_name,
                "sbId": line.extra_info["sbId"],
                "stId": line.extra_info["stId"],
                "depotId": line.extra_info["depotId"],
                "busId": line.bus_num,
                "leaveDate": line.drv_date,
                "beginStationId": line.s_sta_id,
                "endStationId": line.d_sta_id,
                "endStationName": line.d_sta_name,
            }

            check_url = "http://www.bababus.com/ticket/checkBuyTicket.htm"
            r = requests.post(check_url,
                              data=urllib.urlencode(params),
                              headers={"User-Agent": rebot.user_agent, "Content-Type": "application/x-www-form-urlencoded"})
            res = r.json()
            if not res["success"]:
                msg = res["msg"]
                if res["msg"] == "查询失败":
                    lock_result.update({
                        "result_code": 2,
                        "result_reason": msg,
                        "source_account": rebot.telephone,
                    })
                    return lock_result
                else:
                    lock_result.update({
                        "result_code": 0,
                        "result_reason": msg,
                        "source_account": rebot.telephone,
                    })
                    return lock_result

            cookies = json.loads(rebot.cookies)
            form_url = "http://www.bababus.com/order/writeorder.htm"
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
                    "result_code": 0,
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
                "totalPrice": raw_form["totalPrice"],
                "contactName": order.contact_info["name"],
                "contactIdType": "1",
                "contactIdCode": order.contact_info["id_number"],
                "contactPhone": order.contact_info["telephone"],
                "contactEmail": "",
            }
            encode_list= [urllib.urlencode(submit_data),]
            for r in order.riders:
                d = {
                    "psgName": r["name"],
                    "psgIdType": "1",
                    "psgIdCode": r["id_number"],
                    "psgTicketType": 1,
                    "psgBabyFlg": 0,
                    "psgInsuranceTypeId": "",       # 保险
                    "isSave": 0,
                }
                encode_list.append(urllib.urlencode(d))
            encode_str = "&".join(encode_list)
            ret = self.send_lock_request(order, rebot, encode_str)
            errmsg = ret["msg"]
            if ret["success"]:
                expire_time = dte.now()+datetime.timedelta(seconds=15*60)
                order.raw_order_no = ret["content"]
                try:
                    pay_money = self.send_order_request(order)["pay_money"]
                except:
                    pay_money = 0
                lock_result.update({
                    "result_code": 1,
                    "result_reason": errmsg,
                    "pay_url": "",
                    "raw_order_no": ret["content"],
                    "expire_datetime": expire_time,
                    "source_account": rebot.telephone,
                    "pay_money": pay_money,
                })
            else:
                #if u"服务器与客运站网络中断" in errmsg:
                #    body = "源站: 巴巴快巴, <br/> 城市: %s, <br/> 车站: %s" % (line.s_city_name, line.s_sta_name)
                #    async_send_email.delay("客运站联网中断", body)
                if u"错误信息：null" in errmsg:
                    lock_result.update({
                        "result_code": 0,
                        "result_reason": errmsg,
                        "source_account": rebot.telephone,
                    })
                else:
                    lock_result.update({
                        "result_code": 0,
                        "result_reason": errmsg,
                        "source_account": rebot.telephone,
                    })
            return lock_result

    def send_lock_request(self, order, rebot, data):
        """
        单纯向源站发请求
        """
        submit_url = "http://www.bababus.com/order/createorder.htm"
        headers = {
            "User-Agent": rebot.user_agent,
            "Content-Type": "application/x-www-form-urlencoded",
        }
        cookies = json.loads(rebot.cookies)
        resp = requests.post(submit_url, data=data, headers=headers, cookies=cookies)
        ret = resp.json()
        return ret

    def send_order_request(self, order):
        rebot = order.get_lock_rebot()
        detail_url = "http://www.bababus.com/order/detail.htm?busOrderNo=%s" % order.raw_order_no
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
        pay_money = float(re.findall(r"(\d+.\d)",soup.select_one(".order_Aprice").text)[0])
        return {
            "state": soup.select(".pay_success")[0].get_text().split(u"：")[1].strip(),
            "pick_no": no,
            "pick_code": code,
            "pick_site": site,
            "pay_money": pay_money,
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
        ret = self.send_order_request(order)
        state = ret["state"]
        if state == "支付超时作废":
            result_info.update({
                "result_code": 5,
                "result_msg": state,
            })
        elif state == "已作废":
            result_info.update({
                "result_code": 2,
                "result_msg": state,
            })
        elif state == "待出票":
            result_info.update({
                "result_code": 4,
                "result_msg": state,
            })
        elif state=="出票异常":
            self.close_line(order.line, "出票异常")
            result_info.update({
                "result_code": 2,
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
                pay_url = "http://www.bababus.com/order/bankpay.htm"
                headers = {
                    "User-Agent": rebot.user_agent,
                    "Content-Type": "application/x-www-form-urlencoded",
                }
                params = {
                    "payAmount": order.pay_money or order.order_price,
                    "userCouponId": "",
                    "bankCode": "999",
                    "busOrderNo":  order.raw_order_no,
                }
                cookies = json.loads(rebot.cookies)
                r = requests.post(pay_url, data=urllib.urlencode(params), headers=headers, cookies=cookies)
                data = self.extract_alipay(r.content)
                pay_money = float(data["total_fee"])
                trade_no = data["out_trade_no"]
                if order.pay_money != pay_money or order.pay_order_no != trade_no:
                    order.modify(pay_money=pay_money, pay_order_no=trade_no)
                return {"flag": "html", "content": r.content}

        if valid_code:
            info = json.loads(session["pay_login_info"])
            headers = info["headers"]
            cookies = info["cookies"]
            params = {
                "returnurl": "",
                "account": rebot.telephone,
                "password": rebot.password,
                "checkCode": valid_code,
                "rememberMe": 1,
            }
            custom_headers = {}
            custom_headers.update(headers)
            custom_headers.update({"Content-Type": "application/x-www-form-urlencoded"})
            r = requests.post("http://www.bababus.com/login.htm",
                              data=urllib.urlencode(params),
                              headers=custom_headers,
                              allow_redirects=False,
                              cookies=cookies)
            cookies.update(dict(r.cookies))
            rebot.modify(cookies=json.dumps(cookies))
        is_login = rebot.test_login_status()

        if is_login:
            if order.status == STATUS_LOCK_RETRY:
                self.lock_ticket(order)
            return _get_page(rebot)
        else:
            login_form = "http://www.bababus.com/login.htm"
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
        params = {
            "startPlace":line.s_city_name,
            "endPlace": line.d_city_name,
            "sbId": line.extra_info["sbId"],
            "stId": line.extra_info["stId"],
            "depotId": line.extra_info["depotId"],
            "busId": line.bus_num,
            "leaveDate": line.drv_date,
            "beginStationId": line.s_sta_id,
            "endStationId": line.d_sta_id,
            "endStationName": line.d_sta_name,
        }
        now = dte.now()
        check_url = "http://www.bababus.com/ticket/checkBuyTicket.htm"
        ua = random.choice(BROWSER_USER_AGENT)
        r = requests.post(check_url,
                            data=urllib.urlencode(params),
                            headers={"User-Agent": ua, "Content-Type": "application/x-www-form-urlencoded"})
        res = r.json()
        if not res["success"]:
            if res["msg"] != "查询失败":
                result_info.update(result_msg=res["msg"], update_attrs={"left_tickets": 0, "refresh_datetime": now})
                return result_info

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
        try:
            r = requests.post(line_url, data=json.dumps(params), headers=headers)
        except:
            result_info.update(result_msg="exception_ok", update_attrs={"left_tickets": 1, "refresh_datetime": now})
            line_log.info("%s\n%s", "".join(traceback.format_exc()), locals())
            return result_info
        res = r.json()
        if res["returnNo"] != "0000":
            result_info.update(result_msg="error response", update_attrs={"left_tickets": 0, "refresh_datetime": now})
            return result_info

        update_attrs = {}
        for d in res["content"]["busList"]:
            drv_datetime = dte.strptime("%s %s" % (d["leaveDate"], d["leaveTime"]), "%Y-%m-%d %H:%M")
            line_id_args = {
                "s_city_name": line.s_city_name,
                "d_city_name": line.d_city_name,
                "s_sta_name": d["beginStation"],
                "d_sta_name": d["endStation"],
                "crawl_source": line.crawl_source,
                "drv_datetime": drv_datetime,
            }
            line_id = md5("%(s_city_name)s-%(d_city_name)s-%(drv_datetime)s-%(s_sta_name)s-%(d_sta_name)s-%(crawl_source)s" % line_id_args)
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
