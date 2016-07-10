# coding=utf-8

import requests
import re
import time
import json
import urllib

import datetime
import random
from bs4 import BeautifulSoup as bs
# from PIL import Image

from app.constants import *
from datetime import datetime as dte
from app.flow.base import Flow as BaseFlow
from app.models import Line
from app.utils import md5
from app import rebot_log
# import cStringIO
from time import sleep


class Flow(BaseFlow):
    name = 'hn96520'

    # 检测是否取到code
    def check_code_status(self, code, order):
        rebot = order.get_lock_rebot()
        cookies = json.loads(rebot.cookies)
        headers = {'User-Agent': rebot.user_agent}
        url = 'http://www.hn96520.com/member/ajax/checkcode.aspx?code={0}'.format(
            code)
        r = rebot.http_get(url, headers=headers, cookies=cookies)
        if 'true' in r.content:
            order.modify(extra_info={"code": code})
            return 1
        else:
            return 0

    # 锁票
    def do_lock_ticket(self, order, valid_code=""):
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
        if not valid_code or not self.check_code_status(valid_code, order):
            lock_result.update({
                'result_code': 2,
                "lock_info": {"fail_reason": "input_code"}
            })
            return lock_result

        rebot = order.get_lock_rebot()
        riders = rebot.add_riders(order)

        line = order.line
        param = {
            'bc': line.extra_info.get('bc', ''),
            'date': line.extra_info.get('date', ''),
            'global': line.extra_info.get('g', ''),
            'o': '0',
            #'tSum': line.full_price*2,
            'tSum': line.full_price,
            'takemanIds': "," + ",".join(riders),
            'tid': line.extra_info.get('t', ''),
            'txtCode': valid_code,
        }
        url = 'http://www.hn96520.com/putin.aspx?' + urllib.urlencode(param)
        rebot_log.info(url)
        cookies = json.loads(rebot.cookies)
        headers = {'User-Agent': rebot.user_agent}
        # 买票, 添加乘客, 购买班次
        for x in xrange(1):
            r = rebot.http_get(url, headers=headers,
                               cookies=cookies, data=urllib.urlencode(param), timeout=512)
            urlstr = urllib.unquote(r.url.decode('gbk').encode('utf8'))
            tpk = (datetime.datetime.now() + datetime.timedelta(days=1)).strftime('%Y-%m-%d') + ' 09:00'
            tpk = datetime.datetime.strptime(tpk, '%Y-%m-%d %H:%M')
            tpk1 = int(datetime.datetime.now().strftime('%H'))
            if ('333' in urlstr and tpk1 < 17) or  '暂时停止网上售票' in urlstr or '调用异常' in urlstr or '提前' in urlstr or '不足' in urlstr or '不够' in urlstr or '不存在' in urlstr or '停班' in urlstr or 'Unable' in urlstr:
                self.close_line(line)
                errlst = re.findall(r"msg=(\S+)&ErrorUrl", urlstr)
                errmsg = unicode(errlst and errlst[0] or "")
                lock_result.update({
                    'result_code': 0,
                    "source_account": rebot.telephone,
                    "result_reason": errmsg,
                })
                return lock_result
            if '订票结束时间' in urlstr and tpk >= order.line.drv_datetime and tpk1 < 23:
                errlst = re.findall(r"msg=(\S+)&ErrorUrl", urllib.unquote(r.url.decode("gbk").encode("utf8")))
                errmsg = unicode(errlst and errlst[0] or "")
                #rebot_log.info(2333333)
                lock_result.update({
                    'result_code': 0,
                    "source_account": rebot.telephone,
                    "result_reason": errmsg,
                })
                return lock_result
            errlst = re.findall(
                r"msg=(\S+)&ErrorUrl", urllib.unquote(r.url.decode("gbk").encode("utf8")))

            errmsg = unicode(errlst and errlst[0] or "")
            if errmsg:
                lock_result.update({
                    'result_code': 2,
                    "source_account": rebot.telephone,
                    "result_reason": errmsg,
                })
                return lock_result

            soup = bs(r.content, 'lxml')
            title = soup.title
            info = soup.find('table', attrs={
                             'class': 'tblp shadow', 'cellspacing': True, 'cellpadding': True}).find_all('tr')
            pay_money = info[-1].find_all('td')[-1].get_text()
            pay_money = float(re.search(r'\d+', pay_money).group(0))
            raw_order_no = soup.find('input', attrs={'id': 'txt_CopyLink'}).get(
                'value').split('=')[-1]
            if '准备付款' in title:
                expire_time = dte.now() + datetime.timedelta(seconds=15 * 60)
                lock_result.update({
                    'result_code': 1,
                    'raw_order_no': raw_order_no,
                    "expire_datetime": expire_time,
                    "source_account": rebot.telephone,
                    'pay_money': pay_money,
                })
                # 删除之前乘客
                # rebot.clear_riders(riders)
                return lock_result

        errmsg = soup.find(
            'td', attrs={'class': 'mmainbody'}).get_text().strip().encode('utf-8')
        expire_time = dte.now() + datetime.timedelta(seconds=15 * 60)
        lock_result.update({
            'result_code': 2,
            "result_reason": errmsg,
            "expire_datetime": expire_time,
            "source_account": rebot.telephone,
            'pay_money': 0,
        })
        return lock_result

    def send_order_request(self, order):
        rebot = order.get_lock_rebot()
        sn = order.pay_order_no
        sign = SOURCE_INFO.get('hn96520').get(
            'accounts').get(order.source_account)[-2]
        userid = SOURCE_INFO.get('hn96520').get(
            'accounts').get(order.source_account)[-1]
        # sign = '90e7709954c38af7713e1a64bad2012ecd00565e016e16823032e2d465dbd14a'
        username = order.source_account
        password = md5(order.source_account_pass)
        url = 'http://61.163.88.138:8088/auth?UserName={0}&Password={1}&Sign={2}&_={3}&callback=jsonp1'.format(
            username, password, sign, time.time())
        headers = {
            "User-Agent": rebot.user_agent,
        }
        r = rebot.http_get(url, headers=headers, timeout=256)
        # rebot.http_get(url, headers=headers, cookies=r.cookies)
        userid = json.loads(r.content[r.content.index(
            "(") + 1: r.content.rindex(")")]).get('UserId', '')

        ourl = 'http://61.163.88.138:8088/Order/GetMyOrders?UserId={0}&Sign={1}&_={2}&callback=jsonp1'.format(
            userid, sign, time.time())
        r = rebot.http_get(ourl, headers=headers, cookies=r.cookies, timeout=256)
        info = json.loads(r.content[r.content.index(
            "(") + 1: r.content.rindex(")")]).get('OrderList', [])
        for x in info:
            ocode = x['OrderCode']
            if sn == ocode:
                pcode = x.get('Password', '')
                state = x['OrderStatus']

        return {
            "state": state,
            "pick_no": pcode,
            "pick_code": pcode,
            "pick_site": '',
            'raw_order': sn,
            "pay_money": 0.0,
        }

        # ocr方式取票码
        # rebot = order.get_lock_rebot()
        # sn = order.pay_order_no
        # detail_url = 'http://www.hn96520.com/pick.aspx?p={0}'.format(sn)
        # headers = {
        #     "User-Agent": rebot.user_agent,
        # }
        # cookies = json.loads(rebot.cookies)
        # r = rebot.http_get(detail_url, headers=headers, cookies=cookies)
        # soup = bs(r.content, "lxml")
        # info = soup.find(
        #     'table', attrs={'class': 'tblOrder shadow'}).find_all('tr')
        # raw_order = info[1].find('td', attrs={'class': 'c2'}).get_text()
        # state = info[2].find('td', attrs={'class': 'c2'}).get_text()
        # pick_site = info[
        #     4].find('td', attrs={'class': 'c2'}).get_text().split('[')[0]
        # url = 'http://www.hn96520.com/text.aspx?p={0}'.format(sn)
        # from pytesseract import image_to_string
        # from app.utils import ecp
        # r = rebot.http_get(url, headers=headers, cookies=cookies)
        # tmpIm = cStringIO.StringIO(r.content)
        # im = Image.open(tmpIm)
        # im = im.crop((140, 70, 225, 90)).convert(
        #     'L').point(lambda x: 255 if x > 160 else 0)
        # im = ecp(im, 8)
        # code = image_to_string(im, config='-psm 7')
        # return {
        #     "state": state,
        #     "pick_no": code,
        #     "pick_code": code,
        #     "pick_site": pick_site,
        #     'raw_order': raw_order,
        #     "pay_money": 0.0,
        # }

    # 刷新出票
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
        state = ret['state']
        code = ret['pick_code']
        if '已取消' in state:
            result_info.update({
                "result_code": 5,
                "result_msg": state,
            })
        elif '失败' in state:
            result_info.update({
                "result_code": 2,
                "result_msg": state,
            })
        elif '已付款确认' in state and code:
            no, site, raw_order = ret['pick_no'], ret[
                'pick_site'], ret['raw_order']
            dx_info = {
                "time": order.drv_datetime.strftime("%Y-%m-%d %H:%M"),
                "start": order.line.s_sta_name,
                "end": order.line.d_sta_name,
                "code": code,
                "no": no,
                "site": site,
                'raw_order': raw_order,
            }
            dx_tmpl = DUAN_XIN_TEMPL[SOURCE_HN96520]
            code_list = ["%s" % (code)]
            msg_list = [dx_tmpl % dx_info]
            result_info.update({
                "result_code": 1,
                "result_msg": state,
                "pick_code_list": code_list,
                "pick_msg_list": msg_list,
            })
        return result_info

    # 线路刷新, java接口调用
    def do_refresh_line(self, line):
        now = dte.now()
        pre = 'http://www.hn96520.com/placeorder.aspx?'
        params = {
            "start": line.s_city_name,
            "end": line.d_city_name,
            "global": line.extra_info["g"],
            "date": line.extra_info["date"],
        }
        ua = random.choice(BROWSER_USER_AGENT)
        headers = {"User-Agent": ua,
                   "Content-Type": "application/x-www-form-urlencoded"}
        url = pre + urllib.urlencode(params)
        r = requests.get(url, headers=headers, data=params)
        soup = bs(r.content, 'lxml')
        info = soup.find('table', attrs={'class': 'resulttb'}).find_all(
            'tbody', attrs={'class': 'rebody'})
        crawl_source = "hn96520"
        now = dte.now()
        update_attrs = {}
        ft = Line.objects.filter(s_city_name=line.s_city_name,
                                 d_city_name=line.d_city_name, drv_date=line.drv_date)
        t = {x.line_id: x for x in ft}
        s_city_name = line.s_city_name
        update_attrs = {}
        for x in info:
            try:
                bus_num = x.find(
                    'td', attrs={'align': 'center'}).get_text().strip()
                d_city_name = x.find_all('td')[1].get_text().split()[1]
                drv_date = x.find_all('td')[2].get_text().strip()
                drv_time = x.find_all('td')[3].get_text().strip()
                drv_datetime = dte.strptime("%s %s" % (
                    drv_date, drv_time), "%Y-%m-%d %H:%M")
                full_price = float(x.find_all('td')[7].get_text().strip())
                left_tickets = int(x.find_all('td')[8].get_text().strip())
                sts = x.find_all('td')[9].img.get('src', '')
                line_id_args = {
                    's_city_name': s_city_name,
                    'd_city_name': d_city_name,
                    'bus_num': bus_num,
                    'crawl_source': crawl_source,
                    'drv_datetime': drv_datetime,
                }
                line_id = md5(
                    "%(s_city_name)s-%(d_city_name)s-%(drv_datetime)s-%(bus_num)s-%(crawl_source)s" % line_id_args)
                if line_id in t:
                    t[line_id].update(**{"left_tickets": left_tickets, 'full_price': full_price, "refresh_datetime": now})
                if line_id == line.line_id and 'images/bt_yd1.png' != sts:
                    update_attrs = {"left_tickets": left_tickets, 'full_price': full_price, "refresh_datetime": now}
            except Exception as e:
                print(e)

        result_info = {}
        if not update_attrs:
            result_info.update(result_msg="no line info", update_attrs={
                               "left_tickets": 0, "refresh_datetime": now})
        else:
            result_info.update(result_msg="ok", update_attrs=update_attrs)
        return result_info

    def get_pay_page(self, order, valid_code="", session=None, pay_channel="alipay", **kwargs):
        rebot = order.get_lock_rebot()
        is_login = rebot.test_login_status()

        # 登录验证码
        if valid_code and not is_login:
            key = "pay_login_info_%s_%s" % (
                order.order_no, order.source_account)
            info = json.loads(session[key])
            headers = info["headers"]
            cookies = info["cookies"]
            params = {
                "userid": rebot.telephone,
                "pwd": rebot.password,
                "vcode": valid_code,
            }
            custom_headers = {}
            custom_headers.update(headers)
            custom_headers.update(
                {"X-Requested-With": "XMLHttpRequest"})
            custom_headers.update(
                {'Content-Type': 'application/x-www-form-urlencoded; charset=UTF-8'})
            r = rebot.http_post("http://www.hn96520.com/member/ajax/login.aspx",
                                data=urllib.urlencode(params),
                                headers=custom_headers,
                                allow_redirects=False,
                                cookies=cookies)
            cookies.update(dict(r.cookies))
            rebot.modify(cookies=json.dumps(cookies))

        is_login = is_login or rebot.test_login_status()
        if is_login:
            if order.status in [STATUS_LOCK_RETRY, STATUS_WAITING_LOCK]:
                self.lock_ticket(order, valid_code=valid_code)
                order.reload()
                fail_msg = order.lock_info.get("fail_reason", "")
                if fail_msg == "input_code":
                    data = {
                        "cookies": json.loads(rebot.cookies),
                        "headers": {"User-Agent": rebot.user_agent},
                        "valid_url": "http://www.hn96520.com/verifycode.aspx",
                    }
                    key = "pay_login_info_%s_%s" % (
                        order.order_no, order.source_account)
                    session[key] = json.dumps(data)
                    return {"flag": "input_code", "content": ""}

            if order.status == STATUS_WAITING_ISSUE:
                pay_url = "http://www.hn96520.com/pay.aspx"
                headers = {
                    "User-Agent": rebot.user_agent,
                    "Content-Type": "application/x-www-form-urlencoded",
                }
                params = {
                    'o': '0',
                    "h_code": order.raw_order_no,
                    "paymentType": 202,  # alipay参数
                }
                cookies = json.loads(rebot.cookies)
                r = rebot.http_post(pay_url, data=urllib.urlencode(
                    params), headers=headers, cookies=cookies)
                data = self.extract_alipay(r.content)
                pay_money = float(data["total_fee"])
                trade_no = data["out_trade_no"]
                if order.pay_money != pay_money or order.pay_order_no != trade_no:
                    order.modify(pay_money=pay_money, pay_order_no=trade_no, pay_channel='alipay')
                return {"flag": "html", "content": r.content}

        # 未登录
        if not is_login:
            valid_url = 'http://www.hn96520.com/membercode.aspx'
            ua = random.choice(BROWSER_USER_AGENT)
            headers = {"User-Agent": ua}
            data = {
                "cookies": {},
                "headers": headers,
                "valid_url": valid_url,
            }
            key = "pay_login_info_%s_%s" % (
                order.order_no, order.source_account)
            session[key] = json.dumps(data)
            return {"flag": "input_code", "content": ""}
