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
import copy
import urllib2

from datetime import datetime as dte, timedelta
from app.utils import create_validate_code, md5
from app.constants import *
from flask import render_template, request, redirect, url_for, jsonify, session, make_response, flash
from flask.views import MethodView
from flask.ext.login import login_required, current_user
from app.dashboard import dashboard
from app.utils import get_redis
from app.decorators import superuser_required
from app.models import Order, Line, AdminUser, OpenStation, OpenCity
from app.flow import get_flow
from tasks import async_lock_ticket, issued_callback
from app import order_log, db, access_log


@dashboard.before_request
def log_request():
    uname = getattr(current_user, "username", None)
    access_log.info("[request_dashboard] %s %s %s %s", uname, request.environ.get('HTTP_X_REAL_IP', request.remote_addr), request.url, dict(request.form) or "")


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
        if request.args.get("type", "") == "api":  # API登陆, 返回token
            rds = get_redis("default")
            try:
                u = AdminUser.objects.get(username=name, password=md5(pwd), is_removed=0)
                tk = md5(str(time.time()))
                k = "token%s" % tk
                rds.set(k, u.username)
                rds.expire(k, 24*60*60)
                return jsonify({"code": 1, "message": "登陆成功", "token": tk})
            except AdminUser.DoesNotExist:
                return jsonify({"code": 0, "message": "登陆失败"})
        else:                                       # 网页登陆
            session["username"] = name
            session["password"] = pwd
            code = request.form.get("validcode", "")

            if not name.startswith("snmpay") and (not code or code != session.get("img_valid_code")):
                flash("验证码错误", "error")
                return redirect(url_for('dashboard.login'))

            try:
                u = AdminUser.objects.get(username=name, password=md5(pwd), is_removed=0)
                flask_login.login_user(u)
                return redirect(url_for('dashboard.index'))
            except AdminUser.DoesNotExist:
                flash("用户名或密码错误", "error")
                return redirect(url_for('dashboard.login'))


class SubmitOrder(MethodView):
    @login_required
    def get(self, line_id):
        line = Line.objects.get_or_404(line_id=line_id)
        return render_template('dashboard/line-submit.html',
                               line=line,
                               api_url="http://localhost:8000")

    @login_required
    def post(self, line_id):
        line = Line.objects.get_or_404(line_id=line_id)
        fd = request.form
        data = {
            "line_id": line_id,
            "out_order_no": str(int(time.time()*1000)),
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
                {                                                       # 乘客信息
                    "name": fd.get("rider3_name"),                      # 名字
                    "telephone": fd.get("rider3_phone"),                # 手机
                    "id_type": 1,                                       # 证件类型
                    "id_number": fd.get("rider3_idcard"),               # 证件号
                    "age_level": 1,                                     # 大人 or 小孩
                },
            ],
            "locked_return_url": fd.get("lock_url"),
            "issued_return_url": fd.get("issue_url"),
        }

        for d in copy.copy(data["rider_info"]):
            if not d["name"]:
                data["rider_info"].remove(d)
        data["contact_info"] = data["rider_info"][0]
        data["order_price"] = line.real_price()*len(data["rider_info"])

        api_url = urllib2.urlparse.urljoin(fd.get("api_url"), "/orders/submit")
        r = requests.post(api_url, data=json.dumps(data))
        ret = r.json()
        flash(ret["message"])
        return redirect(url_for('dashboard.my_order'))


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

            old_kefu = None
            if order.kefu_username:
                old_kefu = AdminUser.objects.get(username=order.kefu_username)
            order.modify(yc_status=YC_STATUS_ING, kefu_username=kefu, kefu_assigntime=dte.now())
            msg = "%s将单设为异常单, 处理人:%s=>%s 描述:%s" % (current_user.username, getattr(old_kefu, "username", ""), kefu, desc)
            order.add_trace(OT_YICHANG, msg)
            if old_kefu:
                assign.remove_dealing(order, old_kefu)
            access_log.info("[yichangop] %s", msg)
            return jsonify({"code":1, "msg": "设置异常执行成功"})


class ModifyOrderStatusOP(MethodView):
    @login_required
    def get(self, order_no):
        order = Order.objects.get_or_404(order_no=order_no)
        action = request.args.get("action", "set")
        ORDER_STATUS_MSG = {
#             0: "全部订单",
#             STATUS_WAITING_ISSUE: "等待付款",
#             STATUS_WAITING_LOCK: "等待下单",
            STATUS_ISSUE_FAIL: "出票失败",
            STATUS_LOCK_FAIL: "下单失败",
#             STATUS_ISSUE_SUCC: "出票成功",
#             STATUS_GIVE_BACK: "源站已退款",
#             STATUS_ISSUE_ING: "正在出票",
            STATUS_LOCK_RETRY: "下单重试",
        }
        return render_template('dashboard/order-status.html', status_msg=ORDER_STATUS_MSG, order=order, action=action)

    @login_required
    def post(self, order_no):
        order = Order.objects.get_or_404(order_no=order_no)
        status = int(request.form.get("status"))
        desc = request.form.get("desc",'')
        action = request.form.get("action", "set")
        if order.status in [STATUS_ISSUE_SUCC, STATUS_ISSUE_ING, STATUS_LOCK_FAIL]:
            return jsonify({"code": 0, "msg": "%s不允许修改"%STATUS_MSG[order.status]})
        if desc:
            return jsonify({"code": 0, "msg": "描述不能为空"})
        print STATUS_MSG[order.status]
        print STATUS_MSG[status]
        msg = "%s修改订单状态:%s=>%s 描述:%s" % (current_user.username,STATUS_MSG[order.status], STATUS_MSG[status], desc)
        order.add_trace(OT_MODIFY_ORDER_STATUS, msg)
        order.modify(status=status)
        if status in [STATUS_LOCK_FAIL, STATUS_ISSUE_FAIL]:
            now = dte.now()
            if status == STATUS_LOCK_FAIL:
                order.line.modify(left_tickets=0, update_datetime=now, refresh_datetime=now)
            issued_callback.delay(order.order_no)
            return jsonify({"code": 1, "msg": "修改订单状态成功"})
        access_log.info("[modify_order_status] %s", msg)
        return jsonify({"code":1, "msg": "修改订单状态成功"})


def parse_page_data(qs):
    total = qs.count()
    params = request.values.to_dict()
    page = int(params.get("page", 1))
    page_size = int(params.get("page_size", 20))
    if params.get('tab', '') =='yichang':
        page_size = 100
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
    pay_channel = params.get("pay_channel", "")
    if pay_channel:
        query.update(pay_channel=pay_channel)
    order_channel = params.get("order_channel", "")
    if order_channel:
        query.update(order_channel=order_channel)
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
        elif q_key == "channel_order_no":
            query.update(channel_order_no=q_value)

    kefu_name = params.get("kefu_name", "")
    if kefu_name:
        if kefu_name == "None":
            kefu_name=None
        query.update(kefu_username=kefu_name)

    today = dte.now().strftime("%Y-%m-%d")
    str_date = params.get("str_date", "") or today
    end_date = params.get("end_date", "") or today
    query.update(create_date_time__gte=str_date)
    query.update(create_date_time__lt=dte.strptime(end_date, "%Y-%m-%d")+timedelta(days=1))
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
        order_channel_count= {str(d["_id"]["channel"]): d["total"] for d in qs.aggregate({"$group": {"_id": {"channel": "$order_channel"}, "total":{"$sum": 1}}})}

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
                                pay_channel=PAY_CHANNEL,
                                order_channel_count=order_channel_count,
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
                            pay_channel=PAY_CHANNEL,
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


@dashboard.route('/startings', methods=['POST', 'GET'])
@superuser_required
def starting_list():
    params = request.values.to_dict()
    province = params.get("province", "")
    s_city = params.get("s_city", "")
    s_sta = params.get("s_sta", "")
    close_status = params.get("close_status", "")

    city_query = {}
    if province:
        city_query.update(province=province)
    if s_city:
        city_query.update(city_name=s_city)

    sta_query = {}
    if close_status:
        sta_query.update({"close_status": int(close_status)})
    if s_sta:
        sta_query.update(sta_name__contains=s_sta)
    cqs = OpenCity.objects.filter(**city_query)
    qs = OpenStation.objects.filter(city__in=cqs, **sta_query)

    today_str = dte.now().strftime("%Y-%m-%d")
    rds = get_redis("line")
    line_stat = {}
    line_stat["total"] = int(rds.get(RK_DAY_LINE_STAT % (today_str, "total")) or 1)
    line_stat["succ"] = int(rds.get(RK_DAY_LINE_STAT % (today_str, "succ")) or 1)
    line_stat["percent"] = "%.2f%%" % ((line_stat["succ"]* 100)/float(line_stat["total"]))

    return render_template('dashboard/startings.html',
                           page=parse_page_data(qs),
                           source_info=SOURCE_INFO,
                           condition=params,
                           line_stat=line_stat,
                           today_str=today_str,
                           close_status_msg=STATION_CLOSE_MSG,
                           )


@dashboard.route('/startings/set', methods=["POST"])
@superuser_required
def starting_config():
    params = request.values.to_dict()
    action = params.get("name", "") or params.get("action", "")
    if action == "opentime":
        obj= OpenStation.objects.get(id=params["pk"])
        obj.modify(open_time=params["value"])
        obj.clear_cache()
        return jsonify({"code": 1, "msg": "修改售票时间成功" })
    elif action == "endtime":
        obj= OpenStation.objects.get(id=params["pk"])
        obj.modify(end_time=params["value"])
        obj.clear_cache()
        return jsonify({"code": 1, "msg": "修改售票时间成功" })
    elif action == "open_yzcx":
        obj= OpenStation.objects.get(id=params["pk"])
        flag = params["flag"]
        if flag == "true":
            obj.modify(close_status=obj.close_status^STATION_CLOSE_YZCX)
            obj.clear_cache()
            return jsonify({"code": 1, "msg": "打开余票查询"})
        else:
            obj.modify(close_status=obj.close_status|STATION_CLOSE_YZCX)
            obj.clear_cache()
            return jsonify({"code": 1, "msg": "关闭余票查询"})
    elif action == "open_bccx":
        obj= OpenStation.objects.get(id=params["pk"])
        flag = params["flag"]
        if flag == "true":
            obj.modify(close_status=obj.close_status^STATION_CLOSE_BCCX)
            obj.clear_cache()
            return jsonify({"code": 1, "msg": "打开班次查询"})
        else:
            obj.modify(close_status=obj.close_status|STATION_CLOSE_BCCX)
            obj.clear_cache()
            return jsonify({"code": 1, "msg": "关闭班次查询"})
    elif action == "source":
        obj= OpenStation.objects.get(id=params["pk"])
        if params["value"] not in SOURCE_INFO:
            return jsonify({"code": 0, "msg": "参数错误" })
        obj.modify(crawl_source=params["value"])
        obj.clear_cache()
        return jsonify({"code": 1, "msg": "修改售票时间成功" })
    elif action == "weight":
        pk, site = params["pk"].split("_")
        obj= OpenStation.objects.get(id=pk)
        site_list = Line.objects.filter(s_city_name__startswith=obj.city.city_name, s_sta_name=obj.sta_name).distinct("crawl_source")
        data = {k: 1000/(len(site_list)) for k in site_list}
        data.update(obj.source_weight)
        data[site] = int(params["value"])
        obj.modify(source_weight=data)
        obj.clear_cache()
        return jsonify({"code": 1, "msg": "修改权重成功" })
    return jsonify({"code": 0, "msg": "执行失败"})

@dashboard.route('/startings/<station_id>/source', methods=["GET"])
@superuser_required
def starting_source_list(station_id):
    sta_obj = OpenStation.objects.get_or_404(id=station_id)
    data = []
    for s in Line.objects.filter(s_city_name__startswith=sta_obj.city.city_name, s_sta_name=sta_obj.sta_name).distinct("crawl_source"):
        data.append({s: SOURCE_INFO[s]["name"]})
    return json.dumps(data, ensure_ascii=False)


@dashboard.route('/startings/<station_id>/destination', methods=['POST', 'GET'])
@superuser_required
def destionation_list(station_id):
    sta_obj = OpenStation.objects.get_or_404(id=station_id)
    return render_template('dashboard/starting-destination.html',
                           open_station=sta_obj,
                           )


@dashboard.route('/startings/<station_id>/linecount', methods=['POST', 'GET'])
@superuser_required
def line_count_of_starting(station_id):
    sta_obj = OpenStation.objects.get_or_404(id=station_id)
    return render_template('dashboard/starting-linecount.html',
                           open_station=sta_obj,
                           )


@dashboard.route('/startings/<station_id>/ordercount', methods=['POST', 'GET'])
@superuser_required
def order_count_of_starting(station_id):
    sta_obj = OpenStation.objects.get_or_404(id=station_id)
    return render_template('dashboard/starting-ordercount.html',
                           open_station=sta_obj,
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
    elif order.crawl_source in ["bjky", "cqky", 'scqcp', "changtu", 'xintuyun', "hn96520",'szky','fjky','qdky']:
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
    if order.yc_status != YC_STATUS_ING and order.status in [12, 13, 14]:
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
    if order.yc_status != YC_STATUS_ING and (not target.is_switch and target.username not in ["luojunping", "xiangleilei", "chengxiaokang"]):
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
        return render_template('dashboard/error.html', title="出票结束", message="订单已经 %s, 不需要操作" % STATUS_MSG[order.status])
    if order.kefu_username != current_user.username:
        return render_template('dashboard/error.html', title="禁止支付", message="请先要%s把单转给你再支付" % order.kefu_username)
    if order.status == 3 and (dte.now() - order.lock_datetime).total_seconds() > 8*60:
        return render_template('dashboard/error.html', title="禁止支付", message="锁票时间超过8分钟不允许支付")

    rds = get_redis("order")
    key = RK_ORDER_LOCKING % order.order_no
    if rds.get(key):
        return render_template('dashboard/error.html', title="正在锁票", message="正在锁票中, 不用重复点击, 请稍等一段时间后重新打开页面")

    flow = get_flow(order.crawl_source)
    ret = flow.get_pay_page(order, valid_code=code, session=session, bank=current_user.yh_type)
    if not ret:
        ret = {}
    flag = ret.get("flag", "")
    if flag == "url":
        cut = order.pay_money-order.order_price
        if cut and not force:
            msg = "订单金额和支付金额相差 %s 元, 禁止支付!  <a href='%s'>继续支付</a>" % (cut,url_for("dashboard.order_pay", order_no=order.order_no, force=1))
            return render_template('dashboard/error.html', title="禁止支付", message=msg)
        return redirect(ret["content"])
    elif flag == "html":
        cut = order.pay_money-order.order_price
        if cut and not force:
            msg = "订单金额和支付金额相差 %s 元, 禁止支付!  <a href='%s'>继续支付</a>" % (cut,url_for("dashboard.order_pay", order_no=order.order_no, force=1))
            return render_template('dashboard/error.html', title="禁止支付", message=msg)
        return ret["content"]
    elif flag == "input_code":
        return render_template('dashboard/src-code-input.html', order=order, source_info=SOURCE_INFO)
    elif flag == "error":
        return render_template('dashboard/error.html', title="异常页面", message=ret["content"])
    return render_template('dashboard/error.html', title="异常页面", message=str(json.dumps(ret,ensure_ascii = False)))


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
        "ABC": "农业银行",
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
                           tab=request.args.get("tab", "dealing"),
                           rfrom=request.args.get("rfrom", ""))


@dashboard.route('/orders/dealing', methods=['GET'])
@login_required
def dealing_order():
    for o in assign.dealing_orders(current_user):
        if o.status in [STATUS_LOCK_RETRY, STATUS_WAITING_LOCK, STATUS_WAITING_ISSUE]:
            continue
        o.complete_by(current_user)
    total = assign.waiting_lock_size()
    if total > 8:
        kf_order_cnt = 5
    else:
        kf_order_cnt = 3
    rds = get_redis("order")
    key = "assigned:time:%s" % current_user.username

    last_assign = rds.get(key)
    can_refresh = True
    if last_assign and (time.time()-float(last_assign)) < 2.5:  # 请求太频繁
        can_refresh = False

    if current_user.is_switch and not current_user.is_close and can_refresh:
        rds.set(key, time.time())
        for i in range(2):
            order_ct = assign.dealing_size(current_user)
            if order_ct >= kf_order_cnt:
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

    if request.args.get("type", "") == "api":
        lst = []
        for o in qs:
            d = {"order_no": o.order_no, "crawl_source": o.crawl_source, "status":o.status}
            lst.append(d)
        return jsonify({"code":1, "message": "ok", "orders": lst})
    else:
        locking = {}
        dealing_seconds = {}
        for o in qs:
            if rds.get(RK_ORDER_LOCKING % o.order_no):
                locking[o.order_no] = 1
            else:
                locking[o.order_no] = 0
            dealing_seconds[o.order_no] = (dte.now()-o.kefu_assigntime).total_seconds()
        return render_template("dashboard/dealing.html",
                                tab=tab,
                                dealing_seconds=dealing_seconds,
                                page=parse_page_data(qs),
                                status_msg=STATUS_MSG,
                                source_info=SOURCE_INFO,
                                dealing_count=assign.waiting_lock_size()+assign.dealing_size(current_user),
                                dealed_count=dealed_count,
                                yichang_count=yichang_count,
                                all_user=AdminUser.objects.filter(is_removed=0),
                                pay_status_msg = PAY_STATUS_MSG,
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
    access_log.info("[user_switch] %s %s接单", current_user.username, msgs[is_switch])
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
dashboard.add_url_rule("/lines/<line_id>/submit", view_func=SubmitOrder.as_view('submit_order'))
dashboard.add_url_rule("/orders/<order_no>/modify_order_status", view_func=ModifyOrderStatusOP.as_view('modify_order_status'))


@dashboard.route('/users/config', methods=["POST", "GET"])
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
    elif action == u"refresh":
        user = AdminUser.objects.get(username=params["username"])
        info = {
            "dt": dte.now(),
            "yue": float(params.get("yue", 0)),
            "yuebao": float(params.get("yuebao", 0)),
            "account": params.get("account", "")
        }
        user.update(status_check_info=info)
        return jsonify({"code": 1, "msg": "执行成功"})
    return jsonify({"code": 0, "msg": "执行失败"})


@dashboard.route('/orders/<order_no>/addremark', methods=['POST'])
@login_required
def add_order_remark(order_no):
    "增加备注内容"
    order = Order.objects.get_or_404(order_no=order_no)
    content = request.form["content"]
    if not content:
        return jsonify({"code": 0, "msg":"内容不能为空"})
    order.add_trace(OT_REMARK, "%s：%s" % (current_user.username, content))
    return jsonify({"code": 1, "msg": "备注成功加入到追踪列表"})


@dashboard.route('/orders/<order_no>/refresh', methods=['GET'])
def order_refresh(order_no):
    order = Order.objects.get(order_no=order_no)
    flow = get_flow(order.crawl_source)
    flow.refresh_issue(order)
    return redirect(url_for('dashboard.order_list'))


@dashboard.route('/orders/<order_no>/make_fail', methods=['POST'])
@superuser_required
def make_fail(order_no):
    order = Order.objects.get(order_no=order_no)
    content = request.form["content"]
    if order.status not in [7]:
        return jsonify({"code": 1, "msg": "非下单重试的单不允许失败"})
    if not content:
        return jsonify({"code": 0, "msg":"内容不能为空"})
    order.add_trace(OT_REMARK, "%s：%s" % (current_user.username, content))
    order.modify(status=5)
    now = dte.now()
    order.line.modify(left_tickets=0, update_datetime=now, refresh_datetime=now)
    issued_callback.delay(order.order_no)
    return jsonify({"code": 1, "msg": "修改成功"})
