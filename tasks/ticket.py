# -*- coding:utf-8 -*-
"""
异步锁票任务
"""
import urllib2
import json

from app.constants import *
from app import celery
from app import order_log
from app.models import Order
from app.flow import get_flow


@celery.task(ignore_result=True)
def async_lock_ticket(order_no):
    """
    请求源网站锁票 + 锁票成功回调

    Return:
        expire_time: "2015-11-11 11:11:11",     # 订单过期时间
        total_price: 322，          # 车票价格
    """
    order = Order.objects.get(order_no=order_no)
    flow = get_flow(order.crawl_source)
    flow.lock_ticket(order)


@celery.task(ignore_result=True)
def issued_callback(order_no):
    """
    出票回调

    Return:
    {
        "code": RET_OK,
        "message": "OK"
        "data":{
            "sys_order_no": "",
            "out_order_no": "",
            "raw_order_no"; "",
            "pick_info":[{
                "pick_code": "1",
                "pck_msg": "2"
            },],
        }
    }
    """
    from app.models import Order
    order = Order.objects.get(order_no=order_no)
    cb_url = order.issued_return_url
    order_log.info("[issue-callback-start] order:%s, callback:%s", order_no, cb_url)
    if not cb_url:
        return
    if order.status == STATUS_ISSUE_SUCC:
        pick_info = []
        for i, code in enumerate(order.pick_code_list):
            pick_info.append({
                "pick_code": code,
                "pick_msg": order.pick_msg_list[i]
                })
        ret = {
            "code": RET_OK,
            "message": "OK",
            "data": {
                "sys_order_no": order.order_no,
                "out_order_no": order.out_order_no,
                "raw_order_no": order.raw_order_no,
                "pick_info": pick_info,
            }
        }
    else:
        ret = {
            "code": RET_ISSUED_FAIL,
            "message": "fail",
            "data": {
                "sys_order_no": order.order_no,
                "out_order_no": order.out_order_no,
                "raw_order_no": order.raw_order_no,
            }
        }
    order_log.info("[issue-callback]%s %s", order_no, str(ret))
    response = urllib2.urlopen(cb_url, json.dumps(ret), timeout=10)
    order_log.info("[issue-callback-response]%s %s", order_no, str(response))
