# -*- coding:utf-8 -*-
import time
import math
import urllib
import requests
import json
import cStringIO
import flask.ext.login as flask_login
import assign
import traceback
import csv
import StringIO

from datetime import datetime as dte
from app.utils import md5, create_validate_code
from app.constants import *
from flask import render_template, request, redirect, url_for, jsonify, session, make_response, flash
from flask.views import MethodView
from flask.ext.login import login_required, current_user
from app.dashboard import dashboard
from app.utils import get_redis
from app.decorators import superuser_required
from app.models import Order, Line, AdminUser
from app.flow import get_flow
from tasks import async_lock_ticket, issued_callback
from app import order_log, db, access_log


@dashboard.route('/logout')
@login_required
def logout():
    flask_login.logout_user()
    flash("退出登录")
    return redirect(url_for('dashboard.login'))


@dashboard.route('/', methods=['GET'])
@login_required
def index():
    return redirect(url_for('dashboard.my_order'))


@dashboard.route('/codeimg')
def get_code_img():
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
            return redirect(url_for("dashboard.index"))
        return render_template('dashboard/login.html')

    def post(self):
        name = request.form.get("username")
        pwd = request.form.get("password")
        session["username"] = name
        session["password"] = pwd
        code = request.form.get("validcode")
        if code != session.get("img_valid_code"):
            flash("验证码错误", "error")
            return redirect(url_for('dashboard.login'))
        try:
            u = AdminUser.objects.get(username=name, password=md5(pwd), is_removed=0)
            flask_login.login_user(u)
            return redirect(url_for('dashboard.index'))
        except AdminUser.DoesNotExist:
            flash("用户名或密码错误", "error")
            return redirect(url_for('dashboard.login'))


class YiChangeOP(MethodView):
    @login_required
    def get(self, order_no):
        order = Order.objects.get_or_404(order_no=order_no)
        users  = AdminUser.objects.filter(is_removed=0)
        action = request.args.get("action", "set")
        return render_template('dashboard/order-yichang.html', order=order, users=users, action=action)

    @login_required
    def post(self, order_no):
        order = Order.objects.get_or_404(order_no=order_no)
        kefu = request.form.get("username")
        desc = request.form.get("desc")
        action = request.form.get("action", "set")
        if action == "del":
            if order.yc_status != YC_STATUS_ING:
                return jsonify({"code":0, "msg": "执行失败, 状态不对"})
            old_kefu = AdminUser.objects.get(username=order.kefu_username)
            order.modify(yc_status=YC_STATUS_DONE, kefu_username=kefu)
            msg = "%s解除异常状态, 处理人:%s=>%s 描述:%s" % (current_user.username, old_kefu.username, kefu, desc)
            order.add_trace(OT_YICHANG2, msg)
            if order.status in [STATUS_WAITING_LOCK, STATUS_WAITING_ISSUE, STATUS_LOCK_RETRY]:
                assign.add_dealing(order, AdminUser.objects.get(username=kefu))
            elif order.status == STATUS_ISSUE_ING:
                assign.add_dealed_but_not_issued(order, AdminUser.objects.get(username=kefu))
            access_log.info("[yichangop] %s", msg)
            return jsonify({"code":1, "msg": "解除异常执行成功"})
        else:
            if order.yc_status == YC_STATUS_ING:
                return jsonify({"code":0, "msg": "执行失败，已经是异常单了"})
            old_kefu = AdminUser.objects.get(username=order.kefu_username)
            order.modify(yc_status=YC_STATUS_ING, kefu_username=kefu)
            msg = "%s将单设为异常单, 处理人:%s=>%s 描述:%s" % (current_user.username, old_kefu.username, kefu, desc)
            order.add_trace(OT_YICHANG, msg)
            assign.remove_dealing(order, old_kefu)
            access_log.info("[yichangop] %s", msg)
            return jsonify({"code":1, "msg": "设置异常执行成功"})


def parse_page_data(qs):
    total = qs.count()
    params = request.values.to_dict()
    page = int(params.get("page", 1))
    page_size = int(params.get("page_size", 20))
    page_num = int(math.ceil(total*1.0/page_size))
    skip = (page-1)*page_size

    cur_range = range(max(1, page-8),  min(max(1, page-8)+16, page_num+1))
    return {
        "total": total,
        "page_size": page_size,         # 每页page_size条记录
        "page_count": page_num,         # 总共有page_num页
        "cur_page": page,               # 当前页
        "previous": max(0, page-1),
        "next": min(page+1, page_num),
        "items": qs[skip: skip+page_size],
        "range": cur_range,             # 分页按钮显示的范围
    }


@dashboard.route('/orders', methods=['GET', 'POST'])
@login_required
def order_list():
    query = {}
    params = request.values.to_dict()

    source = params.get("source", "")
    source_account = params.get("source_account", "")
    if source:
        query.update(crawl_source=source)
        if source_account:
            query.update(source_account=source_account)

    status = int(params.get("status", "0"))
    if status:
        query.update(status=status)
    else:
        params["status"] = "0"

    pay_status = params.get("pay_status", "")
    if pay_status:
        query.update(pay_status=int(pay_status))
    yc_status = params.get("yc_status", "")
    if yc_status:
        query.update(yc_status=int(yc_status))
    q_key = params.get("q_key", "")
    q_value = params.get("q_value", "").strip()

    Q_query = None
    if q_key and q_value:
        if q_key == "contact_phone":
            query.update(contact_info__telephone=q_value)
        elif q_key == "contact_name":
            query.update(contact_info__name=q_value)
        elif q_key == "contact_idcard":
            query.update(contact_info__id_number=q_value)
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
    str_date = params.get("str_date", "") or today+" 00:00"
    end_date = params.get("end_date", "") or today+" 23:59"
    query.update(create_date_time__gte=str_date)
    query.update(create_date_time__lte=end_date)
    params["str_date"] = str_date
    params["end_date"] = end_date

    pay_account = params.get("pay_account", "")
    if pay_account:
        query.update(pay_account=pay_account)

    qs = Order.objects.filter(Q_query, **query).order_by("-create_date_time")
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
        kefu_count = {d["_id"]["kefu_username"]: d["total"] for d in qs.aggregate({"$group": {"_id": {"kefu_username": "$kefu_username"}, "total":{"$sum": 1}}})}
        site_count = {d["_id"]["crawl_source"]: d["total"] for d in qs.aggregate({"$group": {"_id": {"crawl_source": "$crawl_source"}, "total":{"$sum": 1}}})}
        status_count = {str(d["_id"]["status"]): d["total"] for d in qs.aggregate({"$group": {"_id": {"status": "$status"}, "total":{"$sum": 1}}})}
        status_count["0"] = qs.count()
        account_count = {}
        if source:
            account_count = {str(k): v for k,v in qs.filter(crawl_source=source).item_frequencies('source_account', normalize=False).items()}
        stat = {
            "money_total": qs.aggregate_sum("order_price"),
            "order_total": qs.count(),
            "ticket_total": qs.aggregate_sum("ticket_amount")
        }
        return render_template('dashboard/orders.html',
                                page=parse_page_data(qs),
                                status_msg={str(k): v for k,v in STATUS_MSG.items()},
                                pay_status_msg = PAY_STATUS_MSG,
                                yc_status_msg = YC_STAUTS_MSG,
                                source_info=SOURCE_INFO,
                                condition=params,
                                stat=stat,
                                pay_account_list=pay_accounts,
                                kefu_count=kefu_count,
                                status_count=status_count,
                                site_count=site_count,
                                account_count=account_count,
                                all_user=AdminUser.objects.filter(is_removed=0),
                                )


@dashboard.route('/orders/<order_no>', methods=['GET'])
@login_required
def order_detail(order_no):
    order = Order.objects.get_or_404(order_no=order_no)
    return render_template("dashboard/order-item.html",
                            order=order,
                            status_msg=STATUS_MSG,
                            source_info=SOURCE_INFO,
                            pay_status_msg=PAY_STATUS_MSG,
                           )

@dashboard.route('/orders/<order_no>/traces', methods=['GET'])
@login_required
def order_traces(order_no):
    order = Order.objects.get_or_404(order_no=order_no)
    return render_template("dashboard/order-trace.html", order=order)


@dashboard.route('/ajax/query', methods=["GET"])
@login_required
def ajax_query():
    tp = request.args.get("type", '')
    if tp== "account":
        site = request.args.get("site")
        data  = {
            "code": 1,
            "data": SOURCE_INFO[site]["accounts"].keys(),
        }
        return jsonify(data)
    return "fail"


@dashboard.route('/lines', methods=['POST', 'GET'])
@superuser_required
def line_list():
    params = request.values.to_dict()
    lineid = params.get("line_id", "")
    starting_name = params.get("starting", "")
    dest_name = params.get("destination", "")
    crawl_source = params.get("crawl_source", "")
    drv_date = params.get("drv_date", "")
    query = {}
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
    queryset = Line.objects(**query)

    return render_template('dashboard/lines.html',
                           source_info=SOURCE_INFO,
                           sites=queryset.distinct("crawl_source"),
                           page=parse_page_data(queryset),
                           starting=starting_name,
                           destination=dest_name,
                           line_id=lineid,
                           crawl_source=crawl_source,
                           drv_date=drv_date,
                           condition=params,
                           )


@dashboard.route('/orders/<order_no>/srccodeimg', methods=['GET'])
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
    elif order.crawl_source in ["bjky", "cqky", 'scqcp', "changtu"]:
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


@dashboard.route('/orders/changekefu', methods=['POST'])
@login_required
def change_kefu():
    params = request.values.to_dict()
    order_no, kefu_name = params["pk"], params["value"]
    order = Order.objects.get(order_no=order_no)
    if order.status in [12, 13, 14]:
        return jsonify({"code": 0, "msg": "已支付,不许转!"})
    if not kefu_name:
        return jsonify({"code": 0, "msg": "请选择目标账号!"})
    if order.kefu_username != current_user.username:
        return jsonify({"code": 0, "msg": "这个单不是你的!"})
    try:
        target = AdminUser.objects.get(username=kefu_name)
    except:
        msg = "不存在%s这个账号" % kefu_name
        return jsonify({"code": 0, "msg": msg})
    if order.yc_status != YC_STATUS_ING and (not target.is_switch and target.username not in ["luojunping", "xiangleilei"]):
        msg = "%s没在接单，禁止转单给他。" % target.username
        return jsonify({"code": 0, "msg": msg})
    access_log.info("%s 将%s转给 %s", current_user.username, order_no, kefu_name)
    order.update(kefu_username=target.username, kefu_assigntime=dte.now())
    assign.add_dealing(order, target)
    assign.remove_dealing(order, current_user)
    order.add_trace(OT_TRANSFER, "%s 将订单转给 %s" % (current_user.username, target.username))
    msg = "成功转给%s" % target.username
    return jsonify({"code": 1, "msg": msg})


@dashboard.route('/orders/<order_no>/pay', methods=['GET', 'POST'])
@login_required
def order_pay(order_no):
    params = request.values.to_dict()
    order = Order.objects.get(order_no=order_no)
    code = params.get("valid_code", "")
    force = int(params.get("force", "0"))
    if order.status not in [STATUS_WAITING_ISSUE, STATUS_LOCK_RETRY, STATUS_WAITING_LOCK]:
        return "订单已成功或失败,不需要支付"
    if order.kefu_username != current_user.username:
        return "请先要%s把单转给你再支付" % order.kefu_username
    rds = get_redis("order")
    key = RK_ORDER_LOCKING % order.order_no
    if rds.get(key):
        return "正在锁票,请稍后重试   <a href='%s'>点击重试</a>" % url_for("admin.order_pay", order_no=order.order_no)

    flow = get_flow(order.crawl_source)
    ret = flow.get_pay_page(order, valid_code=code, session=session, bank=current_user.yh_type)
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
        return render_template('dashboard/src-code-input.html', order=order, source_info=SOURCE_INFO)
    elif flag == "error":
        return "%s  <a href='%s'>点击重试</a>" % (ret["content"], url_for("admin.order_pay", order_no=order.order_no))
    return "异常页面 %s" % str(json.dumps(ret,ensure_ascii = False))


@dashboard.route('/users', methods=['GET', 'POST'])
@superuser_required
def user_list():
    params = request.values.to_dict()
    tabtype = params.get("tabtype", "all")
    query = {}
    if tabtype == "online":
        query["is_switch"] = 1
    params["tabtype"] = tabtype

    qs = AdminUser.objects.filter(is_removed=0, **query)
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
    return render_template('dashboard/users.html',
                           condition=params,
                           yh_names=yh_dict,
                           stat={"total_user": qs.count()},
                           pay_types=pay_types,
                           source_info=SOURCE_INFO,
                           page=parse_page_data(qs))


@dashboard.route('/orders/my', methods=['GET'])
@login_required
def my_order():
    return render_template("dashboard/my-order.html",
                           tab=request.args.get("tab", "dealing"))


@dashboard.route('/orders/dealing', methods=['GET'])
@login_required
def dealing_order():
    for o in assign.dealing_orders(current_user):
        if o.status in [STATUS_LOCK_RETRY, STATUS_WAITING_LOCK, STATUS_WAITING_ISSUE]:
            continue
        o.complete_by(current_user)
    if current_user.is_switch and not current_user.is_close:
        for i in range(2):
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

            info = {"username": current_user.username}
            desc = "订单分派给操作人员 %s" %  info["username"]
            order.add_trace(OT_ASSIGN, desc, info)
            if order.status == STATUS_WAITING_LOCK:
                async_lock_ticket.delay(order.order_no)

    tab = request.args.get("tab", "dealing")
    qs = assign.dealed_but_not_issued_orders(current_user)
    dealed_count = qs.count()
    yichang_count = Order.objects.filter(kefu_username=current_user.username, yc_status=YC_STATUS_ING).count()
    if tab == "dealing":
        qs = assign.dealing_orders(current_user).order_by("create_date_time")
    elif tab == "yichang":
        qs = Order.objects.filter(kefu_username=current_user.username, yc_status=YC_STATUS_ING)
    rds = get_redis("order")
    locking = {}
    for o in qs:
        if rds.get(RK_ORDER_LOCKING % o.order_no):
            locking[o.order_no] = 1
        else:
            locking[o.order_no] = 0
    return render_template("dashboard/dealing.html",
                            tab=tab,
                            page=parse_page_data(qs),
                            status_msg=STATUS_MSG,
                            source_info=SOURCE_INFO,
                            dealing_count=assign.waiting_lock_size()+assign.dealing_size(current_user),
                            dealed_count=dealed_count,
                            yichang_count=yichang_count,
                            all_user=AdminUser.objects.filter(is_removed=0),
                            locking=locking)


@dashboard.route('/users/switch', methods=['POST'])
@login_required
def user_switch():
    switch = request.form.get('switch', "off")
    is_switch = 0
    if switch == "on":
        is_switch = 1
    msgs = {0: "关闭", 1: "开启"}
    if is_switch != current_user.is_switch:
        current_user.modify(is_switch=is_switch)
    flash("%s接单" % msgs[is_switch])
    return redirect(url_for("dashboard.my_order"))


@dashboard.route('/fangbian/callback', methods=['POST'])
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


dashboard.add_url_rule("/login", view_func=LoginInView.as_view('login'))
dashboard.add_url_rule("/orders/<order_no>/yichang", view_func=YiChangeOP.as_view('yichang'))


@dashboard.route('/users/config', methods=["POST"])
@superuser_required
def user_config():
    params = request.values.to_dict()
    action = params.get("action", '') or params.get("name")
    if action == "yh_type":
        user = AdminUser.objects.get(username=params["pk"])
        user.modify(yh_type=params["value"])
        return jsonify({"code": 1, "msg": "设置网银类型成功" })
    elif action == "jd_type":
        lst = request.form.getlist("value[]")
        user = AdminUser.objects.get(username=params["pk"])
        user.modify(source_include=lst)
        return jsonify({"code": 1, "msg": "设置接单类型成功" })
    elif action == "set_open":
        user = AdminUser.objects.get(username=params["username"])
        flag = params["flag"]
        if flag == "true":
            user.modify(is_close=False)
            access_log.info("[open_account] %s 关闭账号: %s ", current_user.username, user.username)
            return jsonify({"code": 1, "msg": "账号%s开启成功" % user.username})
        else:
            user.modify(is_close=True)
            access_log.info("[open_account] %s 开启账号: %s ", current_user.username, user.username)
            return jsonify({"code": 1, "msg": "账号%s关闭成功" % user.username})
    return jsonify({"code": 0, "msg": "执行失败"})


@dashboard.route('/orders/<order_no>/addremark', methods=['POST'])
@superuser_required
def add_order_remark(order_no):
    "增加备注内容"
    order = Order.objects.get_or_404(order_no=order_no)
    content = request.form["content"]
    if not content:
        return jsonify({"code": 0, "msg":"内容不能为空"})
    order.add_trace(OT_REMARK, "%s：%s" % (current_user.username, content))
    return jsonify({"code": 1, "msg": "备注成功加入到追踪列表"})
