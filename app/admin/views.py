# -*- coding:utf-8 -*-
import math

from flask import render_template, request
from flask.views import MethodView
from app.admin import admin
from app.models import Order, Line

def parse_page_data(qs):
    total = qs.count()
    page = int(request.args.get("page", default=1))
    pageCount=int(request.args.get("pageCount", default=10))
    pageNum=int(math.ceil(total*1.0/pageCount))
    skip = (page-1)*pageCount
    range_min = max(1, page-5)
    range_max = min(range_min+10, pageNum)
    return {
        "total":total,
        "pageCount":pageCount,
        "pageNum":pageNum,
        "page":page,
        "skip": skip,
        "previous":page-1,
        "next":page+1,
        "range": range(range_min, range_max),
        "items": qs[skip: skip+pageCount]
        }

@admin.route('/', methods=['GET'])
@admin.route('/orders', methods=['GET'])
def order_list():
    return render_template('admin/order_list.html', page=parse_page_data(Order.objects))

@admin.route('/lines', methods=['GET'])
def line_list():
    return render_template('admin/line_list.html', page=parse_page_data(Line.objects))


class SubmitOrder(MethodView):
    def get(self):
        return render_template('admin/submit_order.html', item=None)

    def post(self):
        pass


admin.add_url_rule("/submit_order", view_func=SubmitOrder.as_view('submit_order'))
