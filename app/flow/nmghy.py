#!/usr/bin/env python
# encoding: utf-8

import requests
import json
import urllib
import urlparse

import datetime
import random
from lxml import etree
from bs4 import BeautifulSoup

from app.constants import *
from app.flow.base import Flow as BaseFlow
from app.models import NmghyWebRebot, Line
from datetime import datetime as dte
from app.utils import md5
from app import order_log, line_log


class Flow(BaseFlow):

    name = "nmghy"

    def do_lock_ticket(self, order):
        with NmghyWebRebot.get_and_lock(order) as rebot:
            if not rebot.test_login_status():
                rebot.login()
                rebot.reload()
            self.send_check_request(rebot, order)
            line = order.line
            params = {
                    "bf": "2",
                    "bxFlag": "",
                    "cardtype": '0',
                    "ceti_no": '',
                    "dd_city": line.d_sta_name,
                    "departdate": line.drv_date,
                    "errorMsg": '',
                    "full_price": int(line.full_price),
                    "half_price": int(round(line.full_price/2.0)),
                    "ispost": "1",
                    "max_tickets": '5',
                    "mobile": "",
                    "realname": '',
                    "schedulecode": line.bus_num,
                    "start_city": line.s_sta_name,
               }
            params = urllib.urlencode(params)
            riders = order.riders
            count = len(riders)
            tmp = {}
            for i in range(count):
                tmp = {
                    "psgIdCode[]": riders[i]["id_number"],
                    "psgIdType[]": '0',
                    "psgName[]": riders[i]["name"],
                    "psgTel[]": riders[i]["telephone"],
                    "psgTicketType[]": '0'
                }
                params = params+'&'+urllib.urlencode(tmp)

            order_log.info("[lock-start] order: %s,account:%s start  lock request", order.order_no, rebot.telephone)
            try:
                res = self.send_lock_request(order, rebot, data=params)
            except Exception, e:
                order_log.info("[lock-end] order: %s,account:%s lock request error %s", order.order_no, rebot.telephone,e)
                rebot.login()
                rebot.reload()
                res = self.send_lock_request(order, rebot, data=params)
            order_log.info("[lock-end] order: %s,account:%s lock request result : %s", order.order_no, rebot.telephone,res)

            lock_result = {
                "lock_info": res,
                "source_account": rebot.telephone,
                "pay_money": line.real_price()*order.ticket_amount,
            }
            if res:
                expire_time = dte.now()+datetime.timedelta(seconds=28*60)
                lock_result.update({
                    "result_code": 1,
                    "result_reason": "",
                    "pay_url": "",
                    "raw_order_no": res['raw_order_no'],
                    "expire_datetime": expire_time,
                    "lock_info": res
                })
            else:
#                 errmsg = res['values']['result'].replace("\r\n", " ")
#                 for s in ["剩余座位数不足"]:
#                     if s in errmsg:
#                         self.close_line(line, reason=errmsg)
#                         break
                lock_result.update({
                    "result_code": 0,
                    "result_reason": res,
                    "pay_url": "",
                    "raw_order_no": "",
                    "expire_datetime": None,
                })
            return lock_result
    
    def send_check_request(self, rebot, order):
        """
        单纯向源站发请求
        """
        check_url = "http://www.nmghyjt.com/index.php/busOrder/index/"
        headers = rebot.http_header()
        cookies = json.loads(rebot.cookies)
        data = {
                'ispost': "1",
                'postdata': order.line.extra_info['postdata']
                }
        r = rebot.http_post(check_url, data=data, headers=headers, cookies=cookies)
        content = r.content
        if not isinstance(content, unicode):
            content = content.decode('utf-8')
        sel = etree.HTML(content)
        formObj = sel.xpath('//*[@id="busSearchForm"]/@method')
        if formObj[0] == 'post':
            cookies.update(dict(r.cookies))
            rebot.modify(cookies=json.dumps(cookies))
            return True
        else:
            return False

    def send_lock_request(self, order, rebot, data):
        """
        单纯向源站发请求
        """
        order_url = "http://www.nmghyjt.com/index.php/busOrder/getticket/thispost"
        headers = rebot.http_header()
        cookies = json.loads(rebot.cookies)
        r = rebot.http_post(order_url, data=data, headers=headers, cookies=cookies,allow_redirects=False)
#         proxies = {
#         'http': 'http://192.168.1.33:8888',
#         'https': 'http://192.168.1.33:8888',
#         }
#         r = requests.post(order_url, data=data, headers=headers, cookies=cookies,proxies=proxies,allow_redirects=False)
        print '1111111111', r.content
        location_url = r.headers.get('location', '')
        print '33333333333333333', location_url
        res = {}
        if location_url:
            raw_order_no = location_url.split('/')[6]
            res = {"raw_order_no": raw_order_no}
        return res

    def send_orderDetail_request(self, rebot, order=None, lock_info=None):
        undone_url = "http://www.nmghyjt.com/index.php/busOrder/search_ticket"
        done_url = "http://www.nmghyjt.com/index.php/busOrder/has_ticket"
        tiket_code_url = "http://www.nmghyjt.com/index.php/tiket/index/%s" % order.raw_order_no
        headers = rebot.http_header()
        r = rebot.http_get(tiket_code_url, headers=headers, cookies=json.loads(rebot.cookies))
        content = r.content
        sel = etree.HTML(content)
        pick_no = sel.xpath('//table[@align="center"]/tr/td/table/tr[8]/td[4]/text()')[0].replace(u'\xa0\xa0\xa0', u'')
        pick_code = sel.xpath('//table[@align="center"]/tr/td/table/tr[9]/td[2]/text()')[0].replace(u'\xa0\xa0\xa0', u'')
        res = {
            "state": '',
            "pick_no": '',
            "pick_code": ''
            }
        if pick_code and pick_no:
            res.update({"state": '1',"pick_no": pick_no,"pick_code": pick_code})
        else:
            data = {
                "enddate": str(datetime.date.today()),
                "ispost":  "1/",
                "startdate": str(datetime.date.today()),
            }
    #         r = rebot.http_post(done_url, data=data, headers=headers, cookies=json.loads(rebot.cookies))
    #         content = r.content
    #         sel = etree.HTML(content)
    #         payorderList = sel.xpath('//div[@id="visitorDataTable"]')
    # #         unpayorderList = sel.xpath('//div[@id="visitorDataTable"]/table/tbody/tr')[1:]
    #         if payorderList:
    #             pass
            r = rebot.http_post(undone_url, data=data, headers=headers, cookies=json.loads(rebot.cookies))
            content = r.content
            sel = etree.HTML(content)
            unpayorderList = sel.xpath('//div[@id="visitorDataTable"]/table/tbody/tr')[1:]
            flag = False
            for i in unpayorderList:
                order_no = i.xpath('td[1]/text()')[0]
                status = i.xpath('td[10]/text()')[0]
                print order_no, status
                if order_no == order.raw_order_no:
                    flag = True
                    break
            if flag and status == '已作废':#未支付
                res.update({"state": '2'})
        return res

    def do_refresh_issue(self, order):
        result_info = {
            "result_code": 0,
            "result_msg": "",
            "pick_code_list": [],
            "pick_msg_list": [],
        }
        rebot = NmghyWebRebot.objects.get(telephone=order.source_account)
        if not rebot.test_login_status():
            rebot.login()
            rebot.reload()
        order_log.info("[refresh_issue_start] order: %s,account:%s start orderDetail request", order.order_no, rebot.telephone)
        ret = self.send_orderDetail_request(rebot, order=order)
        order_log.info("[refresh_issue_end] order: %s,account:%s orderDetail request result : %s", order.order_no, rebot.telephone,ret)

        if not order.raw_order_no:
            order.modify(raw_order_no=ret["order_no"])
        state = ret["state"]
        order_status_mapping = {
                "1": "购票成功",
                "2": "已作废",
                }
        if state == "1": #"出票成功":
            pick_no, pick_code = ret["pick_no"], ret["pick_code"]
            dx_info = {
                "order_no": order.raw_order_no,
                "time": order.drv_datetime.strftime("%Y-%m-%d %H:%M"),
                "start": order.line.s_sta_name,
                "end": order.line.d_sta_name,
                "code": pick_code,
                "no": pick_no,
            }
            dx_tmpl = DUAN_XIN_TEMPL[SOURCE_NMGHY]
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
        elif state in ("2"):#取消购票,购票失败,退票成功
            result_info.update({
                "result_code": 2,
                "result_msg": order_status_mapping[state],
            })
        return result_info

    def get_pay_page(self, order, valid_code="", session=None, pay_channel="alipay" ,**kwargs):
        rebot = order.get_lock_rebot()
        headers = rebot.http_header()

        def _get_page(rebot):
            if order.status == STATUS_WAITING_ISSUE:
                order_url = "http://www.nmghyjt.com/index.php/busOrder/zhifu/%s"% order.raw_order_no
                cookies = json.loads(rebot.cookies)
                r = requests.get(order_url, headers=headers, cookies=cookies)
                sel = etree.HTML(r.content)
                cookies.update(dict(r.cookies))
                pay_amounts = sel.xpath('//form[@id="bankPayForm"]/div[@class="l_btn"]/input[@name="pay_amounts"]/@value')[0]
                subject = sel.xpath('//form[@id="bankPayForm"]/div[@class="l_btn"]/input[@name="subject"]/@value')[0]
                orderid = sel.xpath('//form[@id="bankPayForm"]/div[@class="l_btn"]/input[@name="orderid"]/@value')[0]
                pay_url = "http://www.nmghyjt.com/index.php/blank"
                data = {
                        "bankId": "1402",
                        "gateId": "1025",
                        "gateId1": "ali",
                        "gateId5": "upop",
                        "orderid": orderid,
                        "pay_amounts": pay_amounts,
                        "subject": subject
                        }
                if not order.pay_order_no:
                    order.modify(pay_order_no=orderid)
                r = requests.post(pay_url, data=data, headers=headers, cookies=cookies)
                return {"flag": "html", "content": r.content}

        is_login = rebot.test_login_status()

        if is_login:
            if order.status in (STATUS_LOCK_RETRY, STATUS_WAITING_ISSUE):
                self.lock_ticket(order)
            return _get_page(rebot)

    def do_refresh_line(self, line):
        result_info = {
            "result_msg": "",
            "update_attrs": {},
        }
        now = dte.now()
        ua = random.choice(MOBILE_USER_AGENG)
        headers = {"User-Agent": ua}

        line_url = 'http://www.nmghyjt.com/index.php/search/getBuslist'
        data = {
                "dd_city": line.d_sta_name,
                "dd_code": line.d_sta_id,
                "ispost": '1',
                "orderdate": line.drv_date,
                "start_city": line.s_sta_name
                }
        r = requests.post(line_url, data=data, headers=headers)
        content = r.content
        if not isinstance(content, unicode):
            content = content.decode('utf-8')
        sel = etree.HTML(content)
        scheduleList = sel.xpath('//div[@id="visitorDataTable"]/table/tbody/tr')
        if scheduleList:
            for d in scheduleList[1:]:
                bus_num = d.xpath('td[1]/text()')[0]
                drv_time = d.xpath('td[5]/span[@class="lv_time"]/text()')[0]
                price = d.xpath('td[8]/span[@class="tk_price"]/text()')[0]
                left_tickets = d.xpath('td[9]/span/text()')[0]
                postdata = d.xpath('td[10]/a/@onclick')[0].split(',')[1][1:-3]
                drv_datetime = dte.strptime("%s %s" % (line.drv_date, drv_time), "%Y-%m-%d %H:%M")
                line_id_args = {
                    "s_city_name": line.s_city_name,
                    "d_city_name": line.d_city_name,
                    "bus_num": bus_num,
                    "crawl_source": line.crawl_source,
                    "drv_datetime": drv_datetime,
                }
                line_id = md5("%(s_city_name)s-%(d_city_name)s-%(drv_datetime)s-%(bus_num)s-%(crawl_source)s" % line_id_args)
                try:
                    obj = Line.objects.get(line_id=line_id)
                except Line.DoesNotExist:
                    continue
                extra_info = {"postdata": postdata}
                info = {
                    "full_price": float(price),
                    "fee": 0,
                    "left_tickets": int(left_tickets),
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
