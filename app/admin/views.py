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

from datetime import datetime as dte, timedelta
from app.utils import md5, create_validate_code
from app.constants import *
from mongoengine import Q
from flask import render_template, request, redirect, url_for, jsonify, session, make_response
from flask.views import MethodView
from flask.ext.login import login_required, current_user
from app.admin import admin
from app.utils import getRedisObj
from app.models import Order, Line, AdminUser, PushUserList
from tasks import refresh_kefu_order
from tasks import check_order_completed, push_kefu_order
from app.flow import get_flow


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

    old_range = range(max(1, page-8),  min(max(1, page-8)+16, pageNum))
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
        "old_range": old_range,     # 旧管理系统用到
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
    query = {"drv_datetime__gt": dte.now()}
    if lineid:
        query.update(line_id=lineid)
    if starting_name:
        query.update(s_city_name__startswith=starting_name)
    if dest_name:
        query.update(d_city_name__startswith=dest_name)
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
    if order.crawl_source in ["scqcp", "baba"]:
        data = json.loads(session["pay_login_info"])
        code_url = data.get("valid_url")
        headers = data.get("headers")
        cookies = data.get("cookies")
        r = requests.get(code_url, headers=headers, cookies=cookies)
        cookies.update(dict(r.cookies))
        data["cookies"] = cookies
        session["pay_login_info"] = json.dumps(data)
        return r.content
    elif order.crawl_source == "bus100":
        data = json.loads(session["bus100_pay_login_info"])
        code_url = data.get("valid_url")
        headers = data.get("headers")
        cookies = data.get("cookies")
        r = requests.get(code_url, headers=headers, cookies=cookies)
        return r.content


@admin.route('/orders/<order_no>/srccodeinput', methods=['GET'])
@login_required
def src_code_input(order_no):
    order = Order.objects.get(order_no=order_no)
    token = request.args.get("token", "")
    username = request.args.get("username", '')
    return render_template('admin-new/code_input2.html',
                           order=order,
                           token=token,
                           username=username
                           )


@admin.route('/orders/<order_no>/pay', methods=['GET'])
@login_required
def order_pay(order_no):
    order = Order.objects.get(order_no=order_no)
    token = request.args.get("token", "")
    username = request.args.get("username",'')
    if order.status != STATUS_WAITING_ISSUE:
        if order.status == STATUS_LOCK_RETRY:
            pass
        else:
            return redirect(url_for("admin.wating_deal_order"))
    r = getRedisObj()
    try:
        r.set(LAST_PAY_CLICK_TIME % order_no, time.time(), ex=PAY_CLICK_EXPIR)
    except:
        r.set(LAST_PAY_CLICK_TIME % order_no, time.time())
        r.expire(LAST_PAY_CLICK_TIME % order_no, PAY_CLICK_EXPIR)

    code = request.args.get("valid_code", "")
    channel = request.args.get("channel", "alipay")
    flow = get_flow(order.crawl_source)
    ret = flow.get_pay_page(order, valid_code=code, session=session, pay_channel=channel)
    if not ret:
        return redirect(url_for("admin.index"))
    if ret["flag"] == "url":
        return redirect(ret["content"])
    elif ret["flag"] == "html":
        return ret["content"]
    elif ret["flag"] == "input_code":
        if token and token == TOKEN:
            return redirect(url_for("admin.src_code_input", order_no=order_no)+"?token=%s&username=%s"%(TOKEN,username))
        else:
            return redirect(url_for("admin.src_code_input", order_no=order_no))
    elif ret["flag"] == "refuse":
        pass
    return redirect(url_for("admin.wating_deal_order"))


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
            "phone": "18620857607",
            "idcard": "510106199909235149",
        }
        rider1 = {
            "name": "范月芹",
            "phone": "18620857607",
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
    client = request.headers.get("type", 'web')
    query = {}
    if request.method == 'POST':
        status = request.form.get("status", "")
    else:
        status = request.args.get("status", "")

        source = request.args.get("source", "")
        source_account = request.args.get("source_account", "")

        if source:
            query.update(crawl_source=source)
            if source_account:
                query.update(source_account=source_account)
    if status:
        query.update(status=int(status))

    str_date = request.args.get("str_date", "")
    end_date = request.args.get("end_date", "")
    q_key = request.args.get("q_key", "")
    q_value = request.args.get("q_value", "").strip()
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
    kefu_name = request.args.get("kefu_name", "")
    if kefu_name:
        if kefu_name == "None":
            kefu_name=None
        query.update(kefu_username=kefu_name)

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

    kefu_count = {str(k): v for k,v in Order.objects.item_frequencies('kefu_username', normalize=False).items()}

    status_count = {}
    for st in STATUS_MSG.keys():
        status_count[st] = qs.filter(status=st).count()
    stat = {
        "issued_total": int(qs.filter(status=STATUS_ISSUE_SUCC).sum('ticket_amount')),
        "money_total": qs.sum("order_price"),
        "dealed_total": qs.filter(kefu_order_status=1).count(),
        "order_total": qs.count(),
        "status_count": status_count,
        "kefu_count": kefu_count,
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
        page = order_info['page']
        pageCount = order_info['pageCount']
        pageNum = order_info['pageNum']
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

    key = RK_ISSUEING_COUNT
    order_ct = r.scard(key)
    forbid = False
    if order_ct >=3:
        forbid = True

    if userObj.is_kefu:
        key = 'order_list:%s' % userObj.username
        for o in Order.objects.filter(order_no__in=r.smembers(key)):
            if o.status in [STATUS_LOCK_FAIL, STATUS_ISSUE_FAIL, STATUS_ISSUE_SUCC, STATUS_ISSUE_ING, STATUS_GIVE_BACK]:
                o.complete_by(current_user)
#             elif o.status == STATUS_WAITING_LOCK:
#                 r.srem(key, o.order_no)

        if userObj.is_switch:
            order_ct = r.scard(key)
            if order_ct < KF_ORDER_CT:
                count = KF_ORDER_CT-order_ct
                lock_order_list = r.zrange('lock_order_list', 0, -1)
                for i in lock_order_list:
                    if count <= 0:
                        break
                    if forbid and Order.objects.get(order_no=i).crawl_source=="cbd":
                        continue
                    order = Order.objects.get(order_no=i)
                    count -= 1
                    r.zrem('lock_order_list', i)
                    if order.kefu_username:
                        continue
                    order.update(kefu_username=userObj.username)
                    r.sadd(key, i)
                    refresh_kefu_order.apply_async((userObj.username, i))
                    check_order_completed.apply_async((userObj.username, key, i), countdown=4*60)  # 4分钟后执行
                    try:
                        push_kefu_order.apply_async((userObj.username, i))
                    except:
                        pass
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
