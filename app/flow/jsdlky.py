#!/usr/bin/env python
# encoding: utf-8

import random
import requests
import json
import urllib
import datetime

from app.constants import *
from app.flow.base import Flow as BaseFlow
from app.models import Line, JsdlkyWebRebot
from datetime import datetime as dte
from app.utils import md5
from bs4 import BeautifulSoup
from tasks import async_send_email


class Flow(BaseFlow):

    name = "jsdlky"

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
        with JsdlkyWebRebot.get_and_lock(order) as rebot:
            line = order.line
            # 未登录
            if not rebot.test_login_status():
                lock_result.update({
                    "result_code": 2,
                    "source_account": rebot.telephone,
                    "result_reason": u"账号未登录",
                })
                return lock_result

            form_url = "http://www.jslw.gov.cn/busOrder.do"
            params = {
                "event": "init_query",
                "max_date": "2016-04-01",
                "drive_date1": line.drv_date,
                "bus_code": line.bus_num,
                "sstcode": line.extra_info["startstationcode"],
                "rstcode": line.s_sta_id,
                "dstcode": line.d_sta_id,
                "rst_name1": line.s_sta_name,
                "dst_name1": line.d_sta_name,
                "rst_name": line.s_sta_name,
                "dst_name": line.d_sta_name,
                "drive_date": line.drv_date,
                "checkcode": "",
            }
            cookies = json.loads(rebot.cookies)
            headers = {
                "Content-Type": "application/x-www-form-urlencoded",
                "User-Agent": rebot.user_agent,
            }
            r = rebot.http_post(form_url,
                                data=urllib.urlencode(params),
                                headers=headers,
                                cookies=cookies)

            soup = BeautifulSoup(r.content, "lxml")
            # 构造表单参数
            raw_form = {}
            for obj in soup.find_all("input"):
                name, val = obj.get("name"), obj.get("value")
                if name in ["None", "none", '']:
                    continue
                print name, val
                raw_form[name] = val
            return
            # psgName 罗军平
            # psgIdType   01
            # psgIdCode   431021199004165616
            # psgTel  15575101324
            # psgEmail    luo86106@qq.com
            # psgTicketType   0
            # psgBabyFlg  0
            submit_data = {
                "p": raw_form.get("p", ""),
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
                    "saveToName": "",
                    "isSave": 0,
                }
                encode_list.append(urllib.urlencode(d))
            encode_str = "&".join(encode_list)
            ret = self.send_lock_request(order, rebot, encode_str)
            if ret["success"]:
                expire_time = dte.now()+datetime.timedelta(seconds=15*60)
                lock_result.update({
                    "result_code": 1,
                    "result_reason": "%s %s" % (ret["msgType"], ret.get("errorMsg", "")),
                    "pay_url": "",
                    "raw_order_no": ret["billNo"],
                    "expire_datetime": expire_time,
                    "source_account": rebot.telephone,
                })
            else:
                errmsg = ret.get("errorMsg", "").replace("\r\n", " ")
                for s in ["车次停班", "余票不足"]:
                    if s in errmsg:
                        self.close_line(line, reason=errmsg)
                        break
                if u"服务器与客运站网络中断" in errmsg:
                    body = "源站: 巴巴快巴, <br/> 城市: %s, <br/> 车站: %s" % (line.s_city_name, line.s_sta_name)
                    async_send_email.delay("客运站联网中断", body)
                elif "查询车次详情异常" in errmsg:
                    lock_result.update({
                        "result_code": 2,
                        "result_reason": "%s %s" % (ret["msgType"], errmsg),
                    })
                lock_result.update({
                    "result_code": 0,
                    "result_reason": "%s %s" % (ret["msgType"], errmsg),
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
        rebot = JsdlkyWebRebot.objects.get(telephone=order.source_account)
        is_login = rebot.test_login_status()
        if not is_login and valid_code:
            info = json.loads(session["pay_login_info"])
            headers = info["headers"]
            cookies = info["cookies"]
            flag = rebot.login(headers=headers, cookies=cookies, valid_code=valid_code)
            if flag == "OK":
                is_login = 1

        if is_login:
            if order.status == STATUS_LOCK_RETRY:
                self.lock_ticket(order)
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
                data = self.extract_alipay(r.content)
                pay_money = float(data["total_fee"])
                trade_no = data["out_trade_no"]
                if order.pay_money != pay_money or order.pay_order_no != trade_no:
                    order.modify(pay_money=pay_money, pay_order_no=trade_no)
                return {"flag": "html", "content": r.content}
        else:
            login_form = "http://www.jslw.gov.cn/login.do"
            headers = {"User-Agent": random.choice(BROWSER_USER_AGENT)}
            r = requests.get(login_form, headers=headers)
            data = {
                "cookies": dict(r.cookies),
                "headers": headers,
                "valid_url": "http://www.jslw.gov.cn/verifyCode",
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

        update_attrs = {}
        for d in res["content"]["busList"]:
            drv_datetime = dte.strptime("%s %s" % (d["leaveDate"], d["leaveTime"]), "%Y-%m-%d %H:%M")
            line_id_args = {
                "s_city_name": line.s_city_name,
                "d_city_name": line.d_city_name,
                "bus_num": d["busId"],
                "crawl_source": line.crawl_source,
                "drv_datetime": drv_datetime,
            }
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
