# -*- coding:utf-8 -*-
import time
import math
import copy
import urllib2
import urllib
import requests
import json
import cStringIO
import flask.ext.login as flask_login
import assign
import traceback
import csv
import StringIO
import re

from datetime import datetime as dte
from app.utils import md5, create_validate_code
from app.constants import *
from flask import render_template, request, redirect, url_for, jsonify, session, make_response
from flask.views import MethodView
from flask.ext.login import login_required, current_user
from app.admin import admin
from app.utils import get_redis
from app.models import Order, Line, AdminUser, PushUserList
from app.flow import get_flow
from tasks import push_kefu_order, async_lock_ticket, issued_callback
from app import order_log, db, access_log


def parse_page_data(qs):
    total = qs.count()
    if request.method == 'POST':
        page = int(request.form.get("page", default=1))
        pageCount = int(request.form.get("pageCount", default=20))
    else:
        page = int(request.args.get("page", default=1))
        pageCount = int(request.args.get("pageCount", default=20))
    pageNum = int(math.ceil(total*1.0/pageCount))
    skip = (page-1)*pageCount

    query_dict = {}
    for k in request.args.keys():
        if k == "page":
            continue
        query_dict[k] = request.args.get(k)
    query_string = urllib.urlencode(query_dict)

    old_range = range(max(1, page-8),  min(max(1, page-8)+16, pageNum+1))
    return {
        "total": total,
        "pageCount": pageCount,
        "pageNum": pageNum,
        "page": page,
        "skip": skip,
        "previous": max(1, page-1),
        "next": min(page+1, pageNum),
        "items": qs[skip: skip+pageCount],
        "req_path": "%s?%s" % (request.path, query_string),
        "req_path2": "%s?" % request.path,
        "old_range": old_range,
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
    lineid = request.args.get("line_id", "").strip()
    starting_name = request.args.get("starting", "").strip()
    dest_name = request.args.get("destination", "").strip()
    crawl_source = request.args.get("crawl_source", "").strip()
    drv_date = request.args.get("drv_date", "").strip()
    query = {"drv_datetime__gt": dte.now()}
    if lineid:
        query.update(line_id=lineid)
    if starting_name:
        query.update(s_city_name__startswith=starting_name)
    if dest_name:
        query.update(d_city_name__startswith=dest_name)
    if crawl_source:
        query.update(crawl_source=crawl_source)
    if drv_date:
        query.update(drv_date=drv_date)
    queryset = Line.objects(**query).order_by("full_price")

    return render_template('admin/line_list.html',
                           page=parse_page_data(queryset),
                           starting=starting_name,
                           destination=dest_name,
                           line_id=lineid,
                           crawl_source=crawl_source,
                           drv_date=drv_date,
                           )


@admin.route('/orders/<order_no>/srccodeimg', methods=['GET'])
@login_required
def src_code_img(order_no):
    order = Order.objects.get(order_no=order_no)
    if order.crawl_source == "bus100":
        data = json.loads(session["bus100_pay_login_info"])
        code_url = data.get("valid_url")
        headers = data.get("headers")
        cookies = data.get("cookies")
        r = requests.get(code_url, headers=headers, cookies=cookies)
        return r.content
    elif order.crawl_source in ["bjky", "cqky", 'scqcp', "changtu",'bus365']:
        rebot = order.get_lock_rebot()
        key = "pay_login_info_%s_%s" % (order.order_no, order.source_account)
        data = json.loads(session[key])
        code_url = data.get("valid_url")
        headers = data.get("headers")
        cookies = data.get("cookies")
        for i in range(3):
            r = rebot.http_get(code_url, headers=headers, cookies=cookies)
            if "image" not in r.headers.get('content-type'):
                rebot.modify(ip="")
            else:
                break
        cookies.update(dict(r.cookies))
        data["cookies"] = cookies
        session[key] = json.dumps(data)
        return r.content
    else:
        data = json.loads(session["pay_login_info"])
        code_url = data.get("valid_url")
        headers = data.get("headers")
        cookies = data.get("cookies")
        r = requests.get(code_url, headers=headers, cookies=cookies, verify=False)
        cookies.update(dict(r.cookies))
        data["cookies"] = cookies
        session["pay_login_info"] = json.dumps(data)
        return r.content


@admin.route('/orders/<order_no>/srccodeinput', methods=['GET'])
@login_required
def src_code_input(order_no):
    order = Order.objects.get(order_no=order_no)
    token = request.args.get("token", "")
    username = request.args.get("username", '')
    return render_template('admin-new/code_input.html',
                           order=order,
                           token=token,
                           username=username
                           )


@admin.route('/orders/<order_no>/pay_account_input', methods=['GET'])
@login_required
def pay_account_input(order_no):
    order = Order.objects.get(order_no=order_no)
    token = request.args.get("token", "")
    username = request.args.get("username", '')
    return render_template('admin-new/pay_account_input.html',
                           order=order,
                           token=token,
                           username=username,
                           pay_accounts=PAY_ACCOUNTS
                           )

@admin.route('/orders/<order_no>/change_kefu', methods=['POST'])
@login_required
def change_kefu(order_no):
    order = Order.objects.get(order_no=order_no)
    if order.status in [12, 13, 14]:
        return "已支付,不许转!"
    kefu_name = request.form.get("kefuname", "")
    if not kefu_name:
        return "请选择目标账号!"
    if order.kefu_username != current_user.username:
        return "这个单不是你的!"
    try:
        target = AdminUser.objects.get(username=kefu_name)
    except:
        return "不存在%s这个账号" % kefu_name
    if not target.is_switch and target.username not in ["luojunping", "xiangleilei"]:
        return "%s没在接单，禁止转单给他。" % target.username
    access_log.info("%s 将%s转给 %s", current_user.username, order_no, kefu_name)
    order.update(kefu_username=target.username, kefu_assigntime=dte.now())
    assign.add_dealing(order, target)
    assign.remove_dealing(order, current_user)
    return "成功转给%s" % target.username


@admin.route('/orders/<order_no>/pay', methods=['GET'])
@login_required
def order_pay(order_no):
    order = Order.objects.get(order_no=order_no)
    token = request.args.get("token", "")
    username = request.args.get("username",'')
    code = request.args.get("valid_code", "")
    force = int(request.args.get("force", "0"))
    if order.status not in [STATUS_WAITING_ISSUE, STATUS_LOCK_RETRY, STATUS_WAITING_LOCK]:
        return "订单已成功或失败,不需要支付"
    if order.kefu_username != current_user.username:
        return "请先要%s把单转给你再支付" % order.kefu_username
#     if not order.pay_account:
#         if token and token == TOKEN:
#             return redirect(url_for("admin.pay_account_input", order_no=order_no)+"?token=%s&username=%s"%(TOKEN,username))
#         else:
#             return redirect(url_for("admin.pay_account_input", order_no=order_no))
    rds = get_redis("order")
    key = RK_ORDER_LOCKING % order.order_no
    if rds.get(key):
        return "正在锁票,请稍后重试   <a href='%s'>点击重试</a>" % url_for("admin.order_pay", order_no=order.order_no)

    channel = request.args.get("channel", "alipay")
    bank = request.args.get("bank", "")  #BOCB2C:中国银行 CMB:招商银行 CCB :建设银行  SPABANK:平安银行  SPDB 浦发银行
    if not bank:
        bank = 'BOCB2C'
        if current_user.yh_type:
            bank = current_user.yh_type
    flow = get_flow(order.crawl_source)
    ret = flow.get_pay_page(order, valid_code=code, session=session, pay_channel=channel,bank=bank)
    if not ret:
        ret = {}
    flag = ret.get("flag", "")
    if flag == "url":
        if order.pay_money != order.order_price and not force:
            return "订单金额不等于支付金额, 禁止支付! <a href='%s'>继续支付</a>" % url_for("admin.order_pay", order_no=order.order_no, force=1)
        return redirect(ret["content"])
    elif flag == "html":
        if order.pay_money != order.order_price and not force:
            return "订单金额不等于支付金额, 禁止支付! <a href='%s'>继续支付</a>" % url_for("admin.order_pay", order_no=order.order_no, force=1)
        return ret["content"]
    elif flag == "input_code":
        if token and token == TOKEN:
            return redirect(url_for("admin.src_code_input", order_no=order_no)+"?token=%s&username=%s"%(TOKEN,username))
        else:
            return redirect(url_for("admin.src_code_input", order_no=order_no))
    elif flag == "error":
        return "%s  <a href='%s'>点击重试</a>" % (ret["content"], url_for("admin.order_pay", order_no=order.order_no))
    return "异常页面 %s" % str(json.dumps(ret,ensure_ascii = False))


@admin.route('/orders/<order_no>/refresh', methods=['GET'])
@login_required
def order_refresh(order_no):
    order = Order.objects.get(order_no=order_no)
    flow = get_flow(order.crawl_source)
    flow.refresh_issue(order)
    return redirect(url_for('admin.order_list'))


class SubmitOrder(MethodView):
    @login_required
    def get(self):
        #contact = {
        #    "name": " 张淑瑶",
        #    "phone": "15575101324",
        #    "idcard": "513401199007114628",
        #}
        #rider1 = {
        #    "name": "张淑瑶",
        #    "phone": "15575101324",
        #    "idcard": "513401199007114628",
        #}
        contact = {
            "name": "范月芹",
            "phone": "15575101324",
            "idcard": "510106199909235149",
        }
        rider1 = {
            "name": "范月芹",
            "phone": "15575101324",
            "idcard": "510106199909235149",
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
            "out_order_no": str(int(time.time()*1000)),
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
        if not current_user.is_anonymous:
            return redirect(url_for("admin.index"))
        return render_template('admin-new/login.html')

    def post(self):
        client = request.headers.get("type", 'web')
        name = request.form.get("username")
        pwd = request.form.get("password")
        session["username"] = name
        session["password"] = pwd
        if client == 'web':
            code = request.form.get("validcode")
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
    return render_template("admin-new/top.html")


@admin.route('/left', methods=['GET'])
@login_required
def left_page():
    return render_template("admin-new/left.html")


@admin.route('/alluser', methods=['GET','POST'])
@login_required
def all_adminuser():
    params = request.values.to_dict()
    tabtype = params.get("tabtype", "all")
    query = {}
    if tabtype == "online":
        query["is_switch"] = 1
    qs = AdminUser.objects.filter(**query)
    yh_dict = {
        "BOCB2C": "中国银行",
        "CMB": "招商银行",
        "CCB": "建设银行",
        "SPABANK": "平安银行",
        "SPDB": "浦发银行",
    }
    pay_types = {
        u"yhzf": "银行支付",
        u"zfb": "支付宝",
    }
    return render_template('admin-new/alluser.html',
                           condition=params,
                           yh_names=yh_dict,
                           stat={"total_user": qs.count()},
                           pay_types=pay_types,
                           source_info=SOURCE_INFO,
                           page=parse_page_data(qs))

@admin.route('/allorder', methods=['GET','POST'])
@login_required
def all_order():
    client = request.headers.get("type", 'web')
    query = {}
    params = request.values.to_dict()

    source = params.get("source", "")
    source_account = params.get("source_account", "")
    if source:
        query.update(crawl_source=source)
        if source_account:
            query.update(source_account=source_account)

    status = params.get("status", "")
    if status:
        query.update(status=int(status))

    pay_status = params.get("pay_status", "")
    if pay_status:
        query.update(pay_status=int(pay_status))
    q_key = params.get("q_key", "")
    q_value = params.get("q_value", "").strip()

    Q_query = None
    if q_key and q_value:
        if q_key == "contact_phone":
            query.update(contact_info__telephone=q_value)
        elif q_key == "contact_name":
            query.update(contact_info__name=q_value)
        elif q_key == "sys_order_no":
            query.update(order_no=q_value)
        elif q_key == "out_order_no":
            query.update(out_order_no=q_value)
        elif q_key == "raw_order_no":
            query.update(raw_order_no=q_value)
        elif q_key == "trade_no":
            Q_query = (db.Q(pay_trade_no=q_value)|db.Q(refund_trade_no=q_value))
        elif q_key == "pay_order_no":
            query.update(pay_order_no=q_value)

    kefu_name = params.get("kefu_name", "")
    if kefu_name:
        if kefu_name == "None":
            kefu_name=None
        query.update(kefu_username=kefu_name)

    today = dte.now().strftime("%Y-%m-%d")
    str_date = params.get("str_date", "") or today
    end_date = params.get("end_date", "") or today
    query.update(create_date_time__gte=dte.strptime(str_date, "%Y-%m-%d"))
    query.update(create_date_time__lte=dte.strptime(end_date+" 23:59", "%Y-%m-%d %H:%M"))

    pay_account = params.get("pay_account", "")
    if pay_account:
        query.update(pay_account=pay_account)

    qs = Order.objects.filter(Q_query, **query).order_by("-create_date_time")
    # kefu_count = {str(k): v for k,v in qs.item_frequencies('kefu_username', normalize=False).items()}
    # site_count = {str(k): v for k,v in qs.item_frequencies('crawl_source', normalize=False).items()}
    site_count = {}
    kefu_count = {}
    status_count = {}
    for st in STATUS_MSG.keys():
        status_count[st] = qs.filter(status=st).count()
    stat = {
        "issued_total": int(qs.filter(status=STATUS_ISSUE_SUCC).sum('ticket_amount')),
        "money_total": qs.sum("order_price"),
        "order_total": qs.count(),
        "status_count": status_count,
        "kefu_count": kefu_count,
        "site_count": site_count,
    }
    if client == 'web':
        action = params.get("action", "查询")
        if action == "导出CSV":
            t1 = time.time()
            access_log.info("start export order, %s, condition:%s", current_user.username, request.values.to_dict())
            si = StringIO.StringIO()
            si.write("\xEF\xBB\xBF")
            row_header =[
                (lambda o: "%s," % o.order_no, "系统订单号"),
                (lambda o: "%s," % o.out_order_no, "12308订单号"),
                (lambda o: "%s," % o.raw_order_no, "源站订单号"),
                (lambda o: STATUS_MSG[o.status], "订单状态"),
                (lambda o: "%s," % o.pay_trade_no, "付款流水号"),
                (lambda o: "%s," % o.refund_trade_no, "退款流水号"),
                (lambda o: PAY_STATUS_MSG[o.pay_status], "支付状态"),
                (lambda o: o.kefu_username, "代购人员"),
                (lambda o: o.contact_info["name"], "姓名"),
                (lambda o: "%s," % o.contact_info["telephone"], "手机号"),
                (lambda o: o.create_date_time.strftime("%Y-%m-%d %H:%M:%S"), "下单时间"),
                (lambda o: SOURCE_INFO[o.crawl_source]["name"], "源站"),
                (lambda o: "%s," % o.source_account, "源站账号"),
                (lambda o: o.ticket_amount, "订票数"),
                (lambda o: o.order_price, "订单金额"),
                (lambda o: o.pay_account, "支付账号"),
                (lambda o: o.pay_money, "支付金额"),
                (lambda o: o.refund_money, "退款金额"),
                (lambda o: o.starting_name.split(";")[0], "出发城市"),
                (lambda o: o.starting_name.split(";")[1], "出发站"),
                (lambda o: o.destination_name.split(";")[1], "目的站"),
                (lambda o: o.bus_num, "车次号"),
                (lambda o: o.drv_datetime.strftime("%Y-%m-%d %H:%M"), "出发时间"),
            ]
            cw = csv.DictWriter(si, map(lambda t: t[0], row_header))
            cw.writerow({t[0]: t[1] for t in row_header})
            info_list = []
            for o in qs:
                d = {}
                for t in row_header:
                    func = t[0]
                    d[func] = func(o)
                info_list.append(d)
            cw.writerows(info_list)
            output = make_response(si.getvalue())
            output.headers["Content-Disposition"] = "attachment; filename=%s_%s.csv" % (str_date, end_date)
            output.headers["Content-type"] = "text/csv"
            access_log.info("end export order, %s, time: %s", current_user.username, time.time()-t1)
            return output
        else:
            pay_accounts = qs.distinct("pay_account")
            return render_template('admin-new/allticket_order.html',
                                page=parse_page_data(qs),
                                status_msg=STATUS_MSG,
                                pay_status_msg = PAY_STATUS_MSG,
                                source_info=SOURCE_INFO,
                                condition=request.values.to_dict(),
                                stat=stat,
                                today=today,
                                pay_account_list=pay_accounts,
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
        page = order_info['page']
        pageCount = order_info['pageCount']
        pageNum = order_info['pageNum']
        return jsonify({"status": 0,"total":total,"page":page,"pageCount":pageCount,"pageNum":pageNum, "stat":stat, "data": data})


@admin.route('/myorder', methods=['GET'])
@login_required
def my_order():
    working_kefus = AdminUser.objects.filter(is_kefu=1)
    return render_template("admin-new/my_order.html", working_kefus=working_kefus)


@admin.route('/orders/<order_no>', methods=['GET'])
@login_required
def detail_order(order_no):
    order = Order.objects.get_or_404(order_no=order_no)
    return render_template("admin-new/detail_order.html",
                            order=order,
                            status_msg=STATUS_MSG,
                            source_info=SOURCE_INFO,
                            pay_status_msg=PAY_STATUS_MSG,
                           )


@admin.route('/orders/wating_deal', methods=['GET','POST'])
@login_required
def wating_deal_order():
    """
    等待处理订单列表
    """
    client = request.headers.get("type", 'web')
    if current_user.is_kefu:
        for o in assign.dealing_orders(current_user):
            if o.status in [STATUS_LOCK_RETRY, STATUS_WAITING_LOCK, STATUS_WAITING_ISSUE]:
                continue
            o.complete_by(current_user)
        if current_user.is_switch and not current_user.is_close:
            for i in range(20):
                order_ct = assign.dealing_size(current_user)
                if order_ct >= KF_ORDER_CT:
                    break
                order = assign.dequeue_wating_lock(current_user)
                if not order:
                    continue
                if order.kefu_username:
                    continue
                order.update(kefu_username=current_user.username, kefu_assigntime=dte.now())
                assign.add_dealing(order, current_user)
                if order.status == STATUS_WAITING_LOCK:
                    async_lock_ticket.delay(order.order_no)
                push_kefu_order.apply_async((current_user.username, order.order_no))
    qs = assign.dealing_orders(current_user).order_by("create_date_time")
    rds = get_redis("order")
    is_warn = False
    is_close = False
    if client == 'web':
        locking = {}
        for o in qs:
            if rds.get(RK_ORDER_LOCKING % o.order_no):
                locking[o.order_no] = 1
            else:
                locking[o.order_no] = 0
        if not current_user.is_superuser and not current_user.is_close:
            is_close = False
            for o in qs:
                if not o.kefu_assigntime:
                    continue
                warn_time = (dte.now()-o.kefu_assigntime).total_seconds()
                if warn_time > 15*60:
                    is_close = True
                    break
                elif warn_time >= 3*60 and warn_time < 15*60:
                    is_warn = True
            if is_close:
                current_user.modify(is_close=is_close, is_switch=0)
        not_issued = assign.dealed_but_not_issued_orders(current_user)
        # today = dte.now().strftime("%Y-%m-%d")
        # dealed_count = Order.objects.filter(kefu_username=current_user.username,
        #                                     create_date_time__gte=today,
        #                                     status__in=[STATUS_ISSUE_ING, STATUS_ISSUE_SUCC, STATUS_ISSUE_FAIL]) \
        #                     .item_frequencies("crawl_source")
        dealed_count = {}
        return render_template("admin-new/waiting_deal_order.html",
                               page=parse_page_data(qs),
                               status_msg=STATUS_MSG,
                               source_info=SOURCE_INFO,
                               locking=locking,
                               not_issued=not_issued,
                               dealed_count=dealed_count,
                               is_warn=is_warn)
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
    order_no = request.form.get("order_no", '')
    if not (order_no):
        return jsonify({"status": -1, "msg": "参数错误"})
    orderObj = Order.objects.get(order_no=order_no)
    orderObj.complete_by(current_user)
    return jsonify({"status": 0, "msg": "处理完成"})


@admin.route('/kefu_on_off', methods=['POST'])
@login_required
def kefu_on_off():
    is_switch = int(request.form.get('is_switch', 0))
    if current_user.is_close:
        return jsonify({"status": "1", "msg": "账号已经关闭,请联系技术支持"})
    if current_user.is_switch != is_switch:
        current_user.modify(is_switch=is_switch)
        trans = {0: u"关闭", 1: u"开启"}
        access_log.info("[kefu_on_off] %s %s接单", current_user.username, trans[is_switch])
    return jsonify({"status": "0", "is_switch": is_switch,"msg": "设置成功"})


@admin.route('/orders/set_pay_account', methods=['POST'])
@login_required
def set_pay_account():
    today = dte.now().strftime("%Y-%m-%d")
    order_no = request.form.get("order_no", '')
    pay_account = request.form.get("pay_account", '')
    if not (order_no and pay_account):
        return jsonify({"status": -1, "msg": "参数错误"})
    orderObj = Order.objects.get(order_no=order_no)
    orderObj.modify(pay_account=pay_account)
    areadyOrderCt = Order.objects.filter(status=14, pay_account=pay_account,\
                                         crawl_source=orderObj.crawl_source, create_date_time__gte=today).count()
    limit_payct = SOURCE_INFO.get(orderObj.crawl_source).get('limit_payct', DEFALUT_LIMIT_PAYCT)
    crawl_source_name = SOURCE_INFO.get(orderObj.crawl_source).get('name', '')
    return jsonify({"status": 0, 'areadyOrderCt': areadyOrderCt, "limit_payct":limit_payct,
                    'crawl_source_name': crawl_source_name})


@admin.route('/fangbian/callback', methods=['POST'])
def fangbian_callback():
    try:
        order_log.info("[fanbian-callback] %s", request.get_data())
        args = json.loads(request.get_data())
        data = args["data"]
        service_id = args["serviceID"]
        code = args["code"]
        order = Order.objects.get(order_no=data["merchantOrderNo"])
        if service_id == "B001":    # 锁票回调
            raw_order = data["ticketOrderNo"]
            if code == 2100:
                order.modify(status=STATUS_ISSUE_ING, raw_order_no=raw_order)
                order.on_issueing(reason="code:%s, message:%s" % (code, args["message"]))
            else:
                order.modify(status=STATUS_ISSUE_FAIL, raw_order_no=raw_order)
                order.on_issue_fail(reason="code:%s, message:%s" % (code, args["message"]))
                issued_callback.delay(order.order_no)
        elif service_id == "B002":
            if code == 2102:
                msg = urllib.unquote(data["exData"].decode("gbk").encode('utf-8')).replace(u"【", "").replace(u"】", " ")
                order.modify(status=STATUS_ISSUE_SUCC,
                            pick_code_list=[""],
                            pick_msg_list=[msg])
                order.on_issue_success()
                issued_callback.delay(order.order_no)
            else:
                order.modify(status=STATUS_ISSUE_FAIL)
                order.on_issue_fail(reason="code:%s, message:%s" % (code, args["message"]))
                issued_callback.delay(order.order_no)
    except:
        order_log.error("%s\n%s", "".join(traceback.format_exc()), locals())
        return "error"
    return "success"


@admin.route('/api/qpdx', methods=['POST'])
def qupiao_duanxin():
    """
    Request:
    {
        "recevie_phone": "150xxxxxxx",          # 接收短信的手机号码
        "send_phone"; "10086",                  # 发送短信的号码
        "content": "xxxx",                      # 短信内容
    }

    Response:
    {
        "code": 1                           # 1 成功  0 失败或异常
        "message": "ok":
    }
    """
    data = request.get_data()
    access_log.info("[qupiao_duanxin-1] %s", data)
    post = json.loads(data)
    r_phone = post["receive_phone"].lstrip("+86")
    s_phone = post["send_phone"].lstrip("+86")
    content = post["content"].encode("utf-8")
    today = dte.now().strftime("%Y-%m-%d")
    if content.startswith(u"【同程旅游】"):
        regex = r"【同程旅游】您购买了：(\S{4}-\S{2}-\S{2}\s\S{2}:\S{2})，(\S+) - (\S+)车次为(\S+)的汽车票，取票号：(\d+)，取票密码：(\d+)，座位号：(\d+)"
        try:
            sdate, start, dest, bus, pick_no, pick_code, seat = re.findall(regex, content)[0]
            drv_datetime = dte.strptime(sdate, "%Y-%m-%d %H:%M")
        except Exception, e:
            access_log.info("[qupiao_duanxin-2] ignore, incorrect format, %s", e)
            return jsonify({"code": 0, "message": "incorrect conent format", "data": ""})
        orders = Order.objects.filter(create_date_time__gt=today,
                                      crawl_source=SOURCE_TC,
                                      #source_account__in=[r_phone, s_phone],
                                      pick_code_list__contains="%s|%s" % (pick_no, pick_code))
        if orders:
            access_log.info("[qupiao_duanxin-3] ignore, has matched before")
            return jsonify({"code": 0, "message": "has mached before", "data": ""})
        orders = Order.objects.filter(create_date_time__gt=today,
                                      crawl_source=SOURCE_TC,
                                      status__in=[STATUS_WAITING_ISSUE, STATUS_ISSUE_SUCC, STATUS_ISSUE_ING],
                                      drv_datetime=drv_datetime,
                                      bus_num=bus.strip(),
                                      #source_account__in=[r_phone, s_phone],
                                      starting_name=start.strip().replace("/", ";"),
                                      )
        orders = filter(lambda o: not o.pick_code_list, orders)
        if not orders:
            access_log.error("[qupiao_duanxin-4] not found order!")
            return jsonify({"code": 0, "message": "not found order", "data": ""})
        access_log.info("[qupiao_duanxin-5] mached %s order" % len(orders))
        order = orders[0]

        msg_list = []
        dx_tmpl = DUAN_XIN_TEMPL["江苏"]
        code_list = ["%s|%s" % (pick_no, pick_code)]
        dx_info = {
            "time": order.drv_datetime.strftime("%Y-%m-%d %H:%M"),
            "start": order.line.s_sta_name,
            "end": order.line.d_sta_name,
            "code": pick_code,
            "no": pick_no,
            "bus": order.line.bus_num,
        }
        msg_list = [dx_tmpl % dx_info]
        order.modify(pick_code_list=code_list, pick_msg_list=msg_list)
        issued_callback(order.order_no)
        order_log.info("order:%s set pick msg %s", order.order_no, msg_list[0])

    elif content.startswith(u"【畅途网】"):
        regex = r"【畅途网】您预订的(\S{4}-\S{2}-\S{2}\s\S{2}:\S{2})(\S+) (\S+) 到(\S+)，汽车票(\d+)张，订单总金额：(\S+)元。取票时间：(\S+)。凭取票号(\d+)和密码(\d+)取票，取票地点:(\S+)。请预留取票时间"
        try:
            sdate, start_city, start_sta, dest, amount, money, pick_time, pick_no, pick_code, pick_site = re.findall(regex, content)[0]
        except:
            access_log.info("[qupiao_duanxin] ignore!")
    return jsonify({"code": 1,
                    "message": "OK",
                    "data": ""})


@admin.route('/orders/<order_no>/pickinfo', methods=['POST'])
@login_required
def order_pick_info(order_no):
    """
    提交取票信息
    """
    order = Order.objects.get(order_no=order_no)
    if order.crawl_source == SOURCE_TC:
        if order.status not in [STATUS_WAITING_ISSUE, STATUS_ISSUE_SUCC, STATUS_ISSUE_ING]:
            return u"订单状态不正确"
        pick_pass = request.args.get("pick_pass")
        pick_num = request.args.get("pick_num")
        raw_order = request.args.get("raw_order_no")
        msg_list = []
        dx_tmpl = DUAN_XIN_TEMPL["江苏"]
        code_list = ["%s|%s" % (pick_num, pick_pass)]
        if order.pick_code_list and order.pick_code_list != code_list:
            return "之前已经设置过不同的取票短信"
        if raw_order and order.raw_order_no and raw_order != order.raw_order_no:
            return "源站订单号对应不上"
        dx_info = {
            "time": order.drv_datetime.strftime("%Y-%m-%d %H:%M"),
            "start": order.line.s_sta_name,
            "end": order.line.d_sta_name,
            "code": pick_code,
            "no": pick_no,
            "bus": order.line.bus_num,
        }
        msg_list = [dx_tmpl % dx_info]
        order.modify(pick_code_list=code_list, pick_msg_list=msg_list)
        issued_callback(order.order_no)
        return msg_list[0]
    return "type error"


admin.add_url_rule("/submit_order", view_func=SubmitOrder.as_view('submit_order'))
admin.add_url_rule("/login", view_func=LoginInView.as_view('login'))


@admin.route('/set_yh_type', methods=["GET"])
@login_required
def set_yh_type():
    username = request.args.get("username", '')
    yinhang = request.args.get("yinhang", '') #BOCB2C:中国银行 CMB:招商银行 CCB :建设银行  SPABANK:平安银行  SPDB 浦发银行
    if not (username and yinhang):
        return jsonify({"status": "error", "msg": "参数错误"})
    yh_dict = {
               u"中行":"BOCB2C",
               u"招行":"CMB",
               u"建行":"CCB",
               u"平安":"SPABANK",
               u"浦发":"SPDB",
               }
    yh_type = yh_dict.get(yinhang,'')
    if yh_type not in ("BOCB2C", "CMB", "CCB", "SPABANK", "SPDB"):
        return jsonify({"status": "error", "msg": "银行类型错误 请选择(中行, 招行, 建行,平安,浦发)"})
    orderObj = AdminUser.objects.get(username=username)
    orderObj.modify(yh_type=yh_type)
    return jsonify({"status": "success"})


@admin.route('/users/config', methods=["GET", "POST"])
@login_required
def user_config():
    action = request.args.get("action", '')
    if action == "set_yhtype":
        yh_dict = {
            u"中行":"BOCB2C",
            u"招行":"CMB",
            u"建行":"CCB",
            u"平安":"SPABANK",
            u"浦发":"SPDB",
        }
        user = AdminUser.objects.get(username=request.args["username"])
        user.modify(yh_type=yh_dict[request.args["yhtype"]])
        return "success"
    elif action == "set_source":
        lst = request.args.getlist("sourcetype")
        user = AdminUser.objects.get(username=request.args["username"])
        user.modify(source_include=lst)
        return "success"
    return "fail"


@admin.route('/open_account', methods=['POST'])
@login_required
def open_account():
    username = request.form.get('username', 0)
    userObj = AdminUser.objects.get(username=username)
    if not userObj.is_close:
        return jsonify({"status": "0", "msg": "账号已经开启"})
    userObj.modify(is_close=False)
    access_log.info("[open_account] %s 开启账号: %s ", current_user.username, username)
    return jsonify({"status": "0", "msg": "开启成功"})

