# -*- coding:utf-8 -*-
import time
import math
import copy
import urllib2
import urllib
import requests
import json
import pytesseract
import cStringIO
import flask.ext.login as flask_login

from datetime import datetime as dte, timedelta 
from app.utils import md5, create_validate_code
from app.constants import *
from PIL import Image
from lxml import etree
from mongoengine import Q
from flask import render_template, request, redirect, url_for, jsonify, session, make_response
from flask.views import MethodView
from flask.ext.login import login_required, current_user
from app.admin import admin
from app.utils import getRedisObj
from app.models import Order, Line, Starting, Destination, AdminUser, PushUserList
from tasks import refresh_kefu_order
from tasks import issued_callback, check_order_completed, issue_fail_send_email
from app import order_log


def parse_page_data(qs):
    total = qs.count()
    page = int(request.args.get("page", default=1))
    pageCount = int(request.args.get("pageCount", default=10))
    pageNum = int(math.ceil(total*1.0/pageCount))
    skip = (page-1)*pageCount

    query_dict = {}
    for k in request.args.keys():
        if k == "page":
            continue
        query_dict[k] = request.args.get(k)
    query_string = urllib.urlencode(query_dict)

    return {
        "total": total,
        "pageCount": pageCount,
        "pageNum": pageNum,
        "page": page,
        "skip": skip,
        "previous": page-1,
        "next": page+1,
        "items": qs[skip: skip+pageCount],
        "req_path": "%s?%s" % (request.path, query_string),
        "req_path2": "%s?" % request.path,
    }


@admin.route('/orders', methods=['GET'])
@login_required
def order_list():
    order_no = request.args.get("order_no", "")
    if order_no:
        qs = Order.objects.filter(order_no=order_no)
    else:
        qs = Order.objects
    qs = qs.order_by("-create_date_time")
    accounts = SOURCE_INFO[SOURCE_SCQCP]["accounts"]
    return render_template('admin/order_list.html',
                           page=parse_page_data(qs),
                           status_msg=STATUS_MSG,
                           source_info=SOURCE_INFO,
                           scqcp_accounts=accounts,
                           order_no=order_no,
                           )


@admin.route('/lines', methods=['GET'])
@login_required
def line_list():
    lineid = request.args.get("line_id", "")
    starting_name = request.args.get("starting", "")
    dest_name = request.args.get("destination", "")
    queryset = Line.objects
    query = {"drv_datetime__gt": dte.now()}
    if lineid:
        query.update(line_id=lineid)
    if starting_name:
        qs_starting = Starting.objects(Q(city_name__startswith=starting_name) |
                                       Q(station_name__startswith=starting_name))
        query.update(starting__in=qs_starting)
    if dest_name:
        qs_dest = Destination.objects(Q(city_name__startswith=dest_name) |
                                      Q(station_name__startswith=dest_name))
        query.update(destination__in=qs_dest)
    queryset = Line.objects(**query).order_by("-crawl_datetime")
    return render_template('admin/line_list.html',
                           page=parse_page_data(queryset),
                           starting=starting_name,
                           destination=dest_name,
                           line_id=lineid,
                           )


@admin.route('/orders/<order_no>/srccodeimg', methods=['GET'])
@login_required
def src_code_img(order_no):
    order = Order.objects.get(order_no=order_no)
    if order.crawl_source == "scqcp":
        data = json.loads(session["pay_login_info"])
        code_url = data.get("valid_url")
        headers = data.get("headers")
        cookies = data.get("cookies")
        r = requests.get(code_url, headers=headers, cookies=cookies)
        return r.content


@admin.route('/orders/<order_no>/srccodeinput', methods=['GET'])
@login_required
def src_code_input(order_no):
    order = Order.objects.get(order_no=order_no)
    return render_template('admin-new/code_input2.html',
                           order=order,
                           )


@admin.route('/orders/<order_no>/pay', methods=['GET'])
@login_required
def order_pay(order_no):
    order = Order.objects.get(order_no=order_no)
    if order.status != STATUS_WAITING_ISSUE:
        return jsonify({"status": "status_error", "msg": "不是支付的时候", "data": ""})
    r = getRedisObj()
    try:
        r.set(LAST_PAY_CLICK_TIME % order_no, time.time(), ex=PAY_CLICK_EXPIR)
    except:
        r.set(LAST_PAY_CLICK_TIME % order_no, time.time())
        r.expire(LAST_PAY_CLICK_TIME % order_no, PAY_CLICK_EXPIR)

    code = request.args.get("valid_code", "")
    if order.crawl_source == "scqcp":
        headers = {
            'User-Agent': "Mozilla/5.0 (Windows NT 6.2) AppleWebKit/536.3  (KHTML, like Gecko) Chrome/19.0.1061.0 Safari/536.3",
        }
        pay_url = order.pay_url
        # 验证码处理
        if code:
            data = json.loads(session["pay_login_info"])
            code_url = data["valid_url"]
            headers = data["headers"]
            cookies = data["cookies"]
            token = data["token"]
        else:
            login_form_url = "http://scqcp.com/login/index.html"
            r = requests.get(login_form_url, headers=headers)
            sel = etree.HTML(r.content)
            cookies = dict(r.cookies)
            code_url = sel.xpath("//img[@id='txt_check_code']/@src")[0]
            token = sel.xpath("//input[@id='csrfmiddlewaretoken1']/@value")[0]
            r = requests.get(code_url, headers=headers, cookies=cookies)
            cookies.update(dict(r.cookies))
            tmpIm = cStringIO.StringIO(r.content)
            im = Image.open(tmpIm)
            code = pytesseract.image_to_string(im)

        accounts = SOURCE_INFO[SOURCE_SCQCP]["accounts"]
        passwd, _ = accounts[order.source_account]
        data = {
            "uname": order.source_account,
            "passwd": passwd,
            "code": code,
            "token": token,
        }
        r = requests.post("http://scqcp.com/login/check.json", data=data, headers=headers, cookies=cookies)
        cookies.update(dict(r.cookies))
        ret = r.json()
        if ret["success"]:
            print('登录成功')
            r = requests.get(pay_url, headers=headers, cookies=cookies)
            r_url = urllib2.urlparse.urlparse(r.url)
            if r_url.path in ["/error.html", "/error.htm"]:
                order.modify(status=STATUS_ISSUE_FAIL)

                key = 'scqcp_issue_fail'
                r.sadd(key, order.order_no)
                order_ct = r.scard(key)
                if order_ct > 2:
                    issue_fail_send_email.delay(key)

                order_log.info("[issue-refresh-result] %s fail. get error page.", order.order_no)
                rebot = order.get_rebot()
                if rebot:
                    rebot.remove_doing_order(order)
                issued_callback.delay(order.order_no)
                return jsonify({"status": "error", "msg": u"订单过期", "data": ""})
            sel = etree.HTML(r.content)
            data = dict(
                payid=sel.xpath("//input[@name='payid']/@value")[0],
                bank=sel.xpath("//input[@id='s_bank']/@value")[0],
                plate=sel.xpath("//input[@id='s_plate']/@value")[0],
                plateform="alipay",
                qr_pay_mode=0,
                discountCode=sel.xpath("//input[@id='discountCode']/@value")[0]
            )

            info_url = "http://scqcp.com:80/ticketOrder/middlePay.html"
            r = requests.post(info_url, data=data, headers=headers, cookies=cookies)
            return r.content

        elif ret["msg"] == "验证码不正确":
            print("验证码错误")
            data = {
                "cookies": cookies,
                "headers": headers,
                "valid_url": code_url,
                "token": token,
            }
            session["pay_login_info"] = json.dumps(data)
            return redirect(url_for("admin.src_code_input", order_no=order_no))
    elif order.crawl_source == "bus100":
        pay_url = order.pay_url
        headers = {
            'User-Agent': "Mozilla/5.0 (Windows NT 6.1; WOW64; rv:42.0) Gecko/20100101 Firefox/42.0",
        }
        r = requests.get(pay_url, headers=headers, verify=False)
        cookies = dict(r.cookies)

        sel = etree.HTML(r.content)
        try:
            data = dict(
                orderId=sel.xpath('//form[@id="alipayForm"]/input[@id="alipayOrderId"]/@value')[0],
                orderAmt=sel.xpath('//form[@id="alipayForm"]/input[@id="alipayOrderAmt"]/@value')[0],
            )
        except:
            return redirect(pay_url)
        check_url = 'https://pay.84100.com/payment/alipay/orderCheck.do'

        r = requests.post(check_url, data=data, headers=headers, cookies=cookies, verify=False)
        checkInfo = r.json()
        orderNo = checkInfo['request_so']
        data = dict(
            orderId=sel.xpath('//form[@id="alipayForm"]/input[@id="alipayOrderId"]/@value')[0],
            orderAmt=sel.xpath('//form[@id="alipayForm"]/input[@id="alipayOrderAmt"]/@value')[0],
            orderNo=orderNo,
            orderInfo=sel.xpath('//form[@id="alipayForm"]/input[@name="orderInfo"]/@value')[0],
            count=sel.xpath('//form[@id="alipayForm"]/input[@name="count"]/@value')[0],
            isMobile=sel.xpath('//form[@id="alipayForm"]/input[@name="isMobile"]/@value')[0],
        )

        info_url = "https://pay.84100.com/payment/page/alipayapi.jsp"
        r = requests.post(info_url, data=data, headers=headers, cookies=cookies, verify=False)
        return r.content
    elif order.crawl_source == "ctrip":
        rebot = order.get_rebot()
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
        return redirect(pay_url)
    return redirect(url_for('admin.order_list'))


@admin.route('/orders/<order_no>/refresh', methods=['GET'])
@login_required
def order_refresh(order_no):
    order = Order.objects.get(order_no=order_no)
    order.refresh_issued()
    return redirect(url_for('admin.order_list'))


class SubmitOrder(MethodView):
    @login_required
    def get(self):
        contact = {
            "name": "罗军平",
            "phone": "15575101324",
            "idcard": "431021199004165616",
        }
        rider1 = {
            "name": "罗军平",
            "phone": "15575101324",
            "idcard": "431021199004165616",
        }

        kwargs = dict(
            item=None,
            contact=contact,
            rider1=rider1,
            api_url="http://localhost:8000",
            line_id="",
            order_price=0,
        )
        return render_template('admin/submit_order.html', **kwargs)

    @login_required
    def post(self):
        fd = request.form
        data = {
            "line_id": fd.get("line_id"),
            "out_order_no": "12345678910",
            "order_price": float(fd.get("order_price")),
            "contact_info": {
                "name": fd.get("contact_name"),
                "telephone": fd.get("contact_phone"),
                "id_type": 1,
                "id_number": fd.get("contact_idcard"),
                "age_level": 1,                                         # 大人 or 小孩
            },
            "rider_info": [
                {                                                       # 乘客信息
                    "name": fd.get("rider1_name"),                      # 名字
                    "telephone": fd.get("rider1_phone"),                # 手机
                    "id_type": 1,                                       # 证件类型
                    "id_number": fd.get("rider1_idcard"),               # 证件号
                    "age_level": 1,                                     # 大人 or 小孩
                },
                {                                                       # 乘客信息
                    "name": fd.get("rider2_name"),                      # 名字
                    "telephone": fd.get("rider2_phone"),                # 手机
                    "id_type": 1,                                       # 证件类型
                    "id_number": fd.get("rider2_idcard"),               # 证件号
                    "age_level": 1,                                     # 大人 or 小孩
                },
            ],
            "locked_return_url": fd.get("lock_url"),
            "issued_return_url": fd.get("issue_url"),
        }

        for d in copy.copy(data["rider_info"]):
            if not d["name"]:
                data["rider_info"].remove(d)

        api_url = urllib2.urlparse.urljoin(fd.get("api_url"), "/orders/submit")
        r = requests.post(api_url, data=json.dumps(data))
        return redirect(url_for('admin.order_list'))


# ===================================new admin===============================
@admin.route('/code')
def get_code():
    code_img, strs = create_validate_code()
    buf = cStringIO.StringIO()
    code_img.save(buf, 'JPEG', quality=70)
    buf_str = buf.getvalue()
    response = make_response(buf_str)
    response.headers['Content-Type'] = 'image/jpeg'
    session["img_valid_code"] = strs
    return response


class LoginInView(MethodView):
    def get(self):
        return render_template('admin-new/login.html')

    def post(self):
        client = request.headers.get("type", 'web')
        name = request.form.get("username")
        pwd = request.form.get("password")
        if client == 'web':
            code = request.form.get("validcode")
            print session.get("img_valid_code"),code
            if code != session.get("img_valid_code"):
                return redirect(url_for('admin.login'))
            try:
                u = AdminUser.objects.get(username=name, password=md5(pwd))
                flask_login.login_user(u)
                return redirect(url_for('admin.index'))
            except AdminUser.DoesNotExist:
                return redirect(url_for('admin.login'))
        elif client in ['android', 'ios']:
            try:
                u = AdminUser.objects.get(username=name, password=md5(pwd))
                flask_login.login_user(u)
                clientId = request.form.get("clientId")
                data = {
                    'username': name,
                    "push_id": clientId,
                    "client": client,
                    "update_datetime": dte.now()
                }
                try:
                    pushObj = PushUserList.objects.get(username=name)
                    pushObj.push_id = clientId
                    pushObj.client = client
                    pushObj.update_datetime = dte.now()
                    pushObj.save()
                except PushUserList.DoesNotExist:
                    pushObj = PushUserList(**data)
                    pushObj.save()
                return jsonify({"status": "0", "msg": "登录成功", 'token':TOKEN})
            except AdminUser.DoesNotExist:
                return jsonify({"status": "-1", "msg": "登录失败"})


@admin.route('/logout')
@login_required
def logout():
    flask_login.logout_user()
    return redirect(url_for('admin.login'))


@admin.route('/', methods=['GET'])
@login_required
def index():
    return render_template("admin-new/main.html")


@admin.route('/top', methods=['GET'])
@login_required
def top_page():
    key = 'lock_order_list'
    r = getRedisObj()
    count = r.zcard(key)
    sum = count
    userObjs = AdminUser.objects.filter(is_kefu=1)
    for userObj in userObjs:
        username = userObj.username
        kf_key = 'order_list:%s' % username
        order_ct = r.scard(kf_key)
        sum += order_ct
    return render_template("admin-new/top.html", sum=sum)


@admin.route('/left', methods=['GET'])
@login_required
def left_page():
    return render_template("admin-new/left.html")


@admin.route('/allorder', methods=['GET','POST'])
@login_required
def all_order():
    status = request.args.get("status", "")
    source = request.args.get("source", "")
    source_account = request.args.get("source_account", "")
    str_date = request.args.get("str_date", "")
    end_date = request.args.get("end_date", "")
    client = request.headers.get("type", 'web')
    query = {}
    if status:
        query.update(status=int(status))
    if source:
        query.update(crawl_source=source)
        if source_account:
            query.update(source_account=source_account)

    if str_date:
        query.update(create_date_time__gte=dte.strptime(str_date, "%Y-%m-%d"))
    else:
        str_date = dte.now().strftime("%Y-%m-%d")
        query.update(create_date_time__gte=dte.strptime(str_date, "%Y-%m-%d"))
    if end_date:
        query.update(create_date_time__lte=dte.strptime(end_date, "%Y-%m-%d"))
    else:
        end_date = (dte.now()+timedelta(1)).strftime("%Y-%m-%d")
        query.update(create_date_time__lte=dte.strptime(end_date, "%Y-%m-%d"))
    qs = Order.objects.filter(**query).order_by("-create_date_time")
    stat = {
        "issued_total": qs.filter(status=STATUS_ISSUE_SUCC).sum('ticket_amount'),
        "money_total": qs.sum("order_price"),
        "dealed_total": qs.filter(kefu_order_status=1).count(),
    }
    if client == 'web':
        return render_template('admin-new/allticket_order.html',
                               page=parse_page_data(qs),
                               status_msg=STATUS_MSG,
                               source_info=SOURCE_INFO,
                               condition=request.args,
                               stat=stat,
                               str_date=str_date,
                               end_date=end_date
                               )
    elif client in ['android', 'ios']:
        order_info = parse_page_data(qs)
        orders = order_info['items']
        data = []
        for i in orders:
            tmp = {}
            tmp['out_order_no'] = i.out_order_no
            tmp['create_date_time'] = i.create_date_time.strftime('%Y-%m-%d %H:%M:%S')
            tmp['ticket_amount'] = i.ticket_amount
            tmp['starting_name'] = i.starting_name.split(';')[1]
            tmp['destination_name'] = i.destination_name.split(';')[1]
            tmp['order_price'] = i.order_price
            tmp['status'] = i.status
            tmp['alias_status'] = STATUS_MSG[i.status]
            tmp['crawl_source'] = SOURCE_INFO[i.crawl_source]["name"]
            data.append(tmp)
        total = order_info['total']
        page = order_info['page'],
        pageCount = order_info['pageCount'],
        pageNum = order_info['pageNum'],
        return jsonify({"status": 0,"total":total,"page":page,"pageCount":pageCount,"pageNum":pageNum, "stat":stat, "data": data})

admin.add_url_rule("/submit_order", view_func=SubmitOrder.as_view('submit_order'))
admin.add_url_rule("/login", view_func=LoginInView.as_view('login'))


@admin.route('/myorder', methods=['GET'])
@login_required
def my_order():
    return render_template("admin-new/my_order.html")


@admin.route('/orders/<order_no>', methods=['GET'])
@login_required
def detail_order(order_no):
    order = Order.objects.get_or_404(order_no=order_no)
    return render_template("admin-new/detail_order.html",
                            order=order,
                            status_msg=STATUS_MSG,
                            source_info=SOURCE_INFO,
                           )


@admin.route('/orders/wating_deal', methods=['GET','POST'])
@login_required
def wating_deal_order():
    """
    等待处理订单列表
    """
    userObj = current_user
    order_nos = []
    r = getRedisObj()
    client = request.headers.get("type", 'web')
    if userObj.is_kefu:
        key = 'order_list:%s' % userObj.username
        for o in Order.objects.filter(order_no__in=r.smembers(key)):
            if o.status in [STATUS_LOCK_FAIL, STATUS_ISSUE_FAIL, STATUS_ISSUE_SUCC]:
                o.complete_by(current_user)
            elif o.status == STATUS_WAITING_LOCK:
                r.srem(key, o.order_no)

        if userObj.is_switch:
            order_ct = r.scard(key)
            if order_ct < KF_ORDER_CT:
                count = KF_ORDER_CT-order_ct
                lock_order_list = r.zrange('lock_order_list', 0, count-1)
                for i in lock_order_list:
                    r.zrem('lock_order_list', i)
                    r.sadd(key, i)
                    refresh_kefu_order.apply_async((userObj.username, i))
                    check_order_completed.apply_async((userObj.username, key, i), countdown=4*60)  # 4分钟后执行
                    refresh_kefu_order.apply_async((userObj.username, i))
            order_nos = r.smembers(key)

    qs = Order.objects.filter(order_no__in=order_nos)
    qs = qs.order_by("-create_date_time")
    if client == 'web':
        expire_seconds = {}
        t = time.time()
        for o in qs:
            click_time = r.get(LAST_PAY_CLICK_TIME % o.order_no)
            if not click_time:
                expire_seconds[o.order_no] = 0
                continue
            click_time = float(click_time)
            expire_seconds[o.order_no] = max(0, PAY_CLICK_EXPIR-int(t-click_time))
        return render_template("admin-new/waiting_deal_order.html",
                               page=parse_page_data(qs),
                               status_msg=STATUS_MSG,
                               source_info=SOURCE_INFO,
                               expire_seconds=expire_seconds,
                               )
    elif client in ['android', 'ios']:
        data = []
        for i in qs:
            tmp = {}
            tmp['out_order_no'] = i.out_order_no
            tmp['order_no'] = i.order_no
            tmp['create_date_time'] = i.create_date_time.strftime('%Y-%m-%d %H:%M:%S')
            tmp['ticket_amount'] = i.ticket_amount
            tmp['starting_name'] = i.starting_name.split(';')[1]
            tmp['destination_name'] = i.destination_name.split(';')[1]
            tmp['order_price'] = i.order_price
            tmp['status'] = i.status
            tmp['alias_status'] = STATUS_MSG[i.status]
            tmp['crawl_source'] = SOURCE_INFO[i.crawl_source]["name"]
            data.append(tmp)
        return jsonify({"status": 0, "data": data})


@admin.route('/kefu_complete', methods=['POST'])
@login_required
def kefu_complete():
    userObj = current_user
    order_no = request.form.get("order_no", '')
    if not (order_no):
        return jsonify({"status": -1, "msg": "参数错误"})
    orderObj = Order.objects.get(order_no=order_no)
    orderObj.complete_by(userObj)
    return jsonify({"status": 0, "msg": "处理完成"})


@admin.route('/kefu_on_off', methods=['POST'])
@login_required
def kefu_on_off():
    userObj = AdminUser.objects.get(username=current_user.username)
    is_switch = int(request.form.get('is_switch', 0))

    userObj.is_switch = is_switch
    userObj.save()
    return jsonify({"status": "0", "is_switch": is_switch,"msg": "设置成功"})


@admin.route('/test_pay', methods=['GET'])
def test_ctrip_pay():
    import requests
    login_form = "https://accounts.ctrip.com/member/login.aspx"
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 6.1; WOW64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/46.0.2490.86 Safari/537.36",
    }
    r = requests.get(login_form, headers=headers)
    cookies = r.cookies
    sel = etree.HTML(r.content)
    form_data = {}
    for s in sel.xpath("//input"):
        name = s.get("name")
        if not name:
            continue
        value = s.get("value", "")
        form_data[name] = value
    form_data.update({"txtUserName": "15575101324", "txtPwd": "luoguiyang"})
    form_data.update(hidGohome=form_data["hdnToken"])

    login_url = "https://accounts.ctrip.com/member/login.aspx"
    import urllib
    qstr = urllib.urlencode(form_data)
    r = requests.post(login_url, data=qstr, headers=headers, cookies=cookies, proxies={"http": "http://localhost:8888"})
    cookies = r.cookies

    #url = "https://secure.ctrip.com/RealTimePay/Catalog/Submit/336498767"
    #data = """{"CustomerID":"M302009380","MerchantID":"200093","OrderID":"1574557621","OrderAmount":"15.50","OrderType":"36","RequestID":"336498767","CmoneyPassword":"","CmoneyAmount":0,"CmoneyList":"[]","ElseAmount":15.5,"ElseCatalogCode":"EBank","ElseCode":"Alipay","ElseFee":0,"BankName":"支付宝","ElseNumber":"","ElseEndDate":"","ElseExchangeChannel":"EDC","SmsCodePassed":"F","BrandID":"Alipay","ChannelID":"24","VendorID":"2","CheckPhone":"0"}"""
    #r = requests.post(url, data=data, headers=headers, cookies=cookies)
    return r.content
