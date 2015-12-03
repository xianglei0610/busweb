# -*- coding:utf-8 -*-

from app.admin import admin
from flask import render_template
from app.models import Order

def parse_page_data(qs):
    total=qs.count()
    page=self.get_param("page",TYPE_INT,default=1)
    page = int(request.args.get("page", default=1))
    pageCount=int(request.args.get("pageCount", default=10))
    pageNum=int(math.ceil(total*1.0/pageCount))
    return Dict({
        "total":total,
        "pageCount":pageCount,
        "pageNum":pageNum,
        "page":page,
        "skip":(page-1)*pageCount,
        "previous":page-1,
        "next":page+1,
        })

@admin.route('/', methods=['GET'])
def index():
    orders = Order.objects
    kwargs = {
        "page": parse_page_data,
        "orders": orders,
    }
    return render_template('admin/order_list.html', **kwargs)
