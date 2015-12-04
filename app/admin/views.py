# -*- coding:utf-8 -*-
import math
import urllib2
import urllib
import requests
import json

from app.constants import STATUS_MSG, SOURCE_MSG
from flask import render_template, request, redirect, url_for
from flask.views import MethodView
from app.admin import admin
from app.models import Order, Line


def parse_page_data(qs):
    total = qs.count()
    page = int(request.args.get("page", default=1))
    pageCount = int(request.args.get("pageCount", default=10))
    pageNum = int(math.ceil(total*1.0/pageCount))
    skip = (page-1)*pageCount
    range_min = max(1, page-5)
    range_max = min(range_min+10, pageNum)

    query_dict = dict(request.args)
    if "page" in query_dict:
        del query_dict["page"]
    query_string = urllib.urlencode(query_dict)

    return {
        "total": total,
        "pageCount": pageCount,
        "pageNum": pageNum,
        "page": page,
        "skip": skip,
        "previous": page-1,
        "next": page+1,
        "range": range(range_min, range_max),
        "items": qs[skip: skip+pageCount],
        "req_path": "%s?%s" % (request.path, query_string),
    }


@admin.route('/', methods=['GET'])
@admin.route('/orders', methods=['GET'])
def order_list():
    return render_template('admin/order_list.html',
                           page=parse_page_data(Order.objects.order_by("-create_date_time")),
                           status_msg=STATUS_MSG,
                           source_msg=SOURCE_MSG,
                           )


@admin.route('/lines', methods=['GET'])
def line_list():
    return render_template('admin/line_list.html', page=parse_page_data(Line.objects))


@admin.route('/orders/<order_no>/pay', methods=['GET'])
def order_pay(order_no):
    order = Order.objects.get(order_no=order_no)
    if order.pay_url:
        pay_url = order.pay_url
    else:
        pay_url = "http://www.scqcp.com/ticketOrder/redirectOrder.html?pay_order_id=%s" % order.lock_info["pay_order_id"]
    return redirect(pay_url)


@admin.route('/orders/<order_no>/refresh', methods=['GET'])
def order_refresh(order_no):
    pass


class SubmitOrder(MethodView):
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

        line = Line.objects.first()
        kwargs = dict(
            item=None,
            contact=contact,
            rider1=rider1,
            api_url="http://localhost:8000",
            line_id=line.line_id,
            order_price=line.full_price+line.fee,
        )
        return render_template('admin/submit_order.html', **kwargs)

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

        import copy
        for d in copy.copy(data["rider_info"]):
            if not d["name"]:
                data["rider_info"].remove(d)

        api_url = urllib2.urlparse.urljoin(fd.get("api_url"), "/orders/submit")
        res = requests.post(api_url, data=json.dumps(data))
        print "submit order", res
        return redirect(url_for('admin.order_list'))


admin.add_url_rule("/submit_order", view_func=SubmitOrder.as_view('submit_order'))
