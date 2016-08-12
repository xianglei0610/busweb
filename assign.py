#!/usr/bin/env python
# encoding: utf-8
import time

from app.constants import *
from app.utils import get_redis
from app.models import Order
from datetime import datetime as dte


def enqueue_wating_lock(order):
    """
    等待下单队列
    """
    now = dte.now()
    line = order.line
    rds = get_redis("order")
    val = "%s_%s" % (order.order_no, int(time.time()*1000))

    if (line.drv_datetime-now).total_seconds() <= 3*60*60+20:       # 3个小时内的车优先处理
        if order.crawl_source in [SOURCE_BJKY, SOURCE_HEBKY, SOURCE_SCQCP,
                                  SOURCE_SZKY, SOURCE_ZHW, SOURCE_BUS365, SOURCE_GLCX,SOURCE_FJKY]: # 银行支付
            rds.lpush(RK_ORDER_QUEUE_YH2, val)
        else:
            rds.lpush(RK_ORDER_QUEUE_ZFB2, val)
    else:
        if order.crawl_source in [SOURCE_BJKY, SOURCE_HEBKY,SOURCE_SCQCP,
                                  SOURCE_SZKY, SOURCE_ZHW, SOURCE_BUS365, SOURCE_GLCX,SOURCE_FJKY]: # 银行支付
            rds.lpush(RK_ORDER_QUEUE_YH, val)
        else:
            rds.lpush(RK_ORDER_QUEUE_ZFB, val)


def dequeue_wating_lock(user):
    rds = get_redis("order")

    def _cmp_rpop(k1, k2):
        v1, v2 = rds.lindex(k1, -1), rds.lindex(k2, -1)
        if v1 and v2:
            v1, t1 = v1.split("_")
            v2, t2 = v2.split("_")
            if t1 > t2:
                return rds.rpop(k2)
            return rds.rpop(k1)
        elif v1:
            v1, t1 = v1.split("_")
            return rds.rpop(k1)
        elif v2:
            v2, t2 = v2.split("_")
            return rds.rpop(k2)
        return ""


    val = ""
    if "yhzf" in user.source_include and "zfb" in user.source_include:
        val = _cmp_rpop(RK_ORDER_QUEUE_YH2, RK_ORDER_QUEUE_ZFB2)
        if not val:
            val = _cmp_rpop(RK_ORDER_QUEUE_YH, RK_ORDER_QUEUE_ZFB)
    elif "yhzf" in user.source_include:
        val = rds.rpop(RK_ORDER_QUEUE_YH2)
        if not val:
            val = rds.rpop(RK_ORDER_QUEUE_YH)
    elif "zfb" in user.source_include:
        val = rds.rpop(RK_ORDER_QUEUE_ZFB2)
        if not val:
            val = rds.rpop(RK_ORDER_QUEUE_ZFB)

    if val:
        no, t = val.split("_")
        return Order.objects.get(order_no=no)
    return None


def waiting_lock_size():
    rds = get_redis("order")
    return rds.llen(RK_ORDER_QUEUE_YH) + rds.llen(RK_ORDER_QUEUE_YH2)+ \
           rds.llen(RK_ORDER_QUEUE_ZFB) + rds.llen(RK_ORDER_QUEUE_ZFB2)


def add_dealing(order, user):
    """
    分配给代购人员的单
    """
    rds = get_redis("order")
    key = RK_DEALING_ORDERS % user.username
    rds.sadd(key, order.order_no)


def remove_dealing(order, user):
    rds = get_redis("order")
    key = RK_DEALING_ORDERS % user.username
    rds.srem(key, order.order_no)


def dealing_size(user):
    rds = get_redis("order")
    key = RK_DEALING_ORDERS % user.username
    return rds.scard(key)


def dealing_orders(user):
    rds = get_redis("order")
    key = RK_DEALING_ORDERS % user.username
    s_all = rds.smembers(key)
    qs = Order.objects.filter(order_no__in=s_all)
    s_exists = set(qs.distinct("order_no"))
    s_null = s_all-s_exists
    if s_null:
        rds.srem(key, *list(s_null))
    return qs


def add_dealed_but_not_issued(order, user):
    if order.status in [STATUS_GIVE_BACK, STATUS_ISSUE_SUCC, STATUS_ISSUE_FAIL, STATUS_LOCK_FAIL]:
        return
    rds = get_redis("order")
    key = RK_DEALED_NOT_ISSUED % user.username
    rds.sadd(key, order.order_no)


def dealed_but_not_issued_orders(user):
    rds = get_redis("order")
    key = RK_DEALED_NOT_ISSUED % user.username
    s_all = set(rds.smembers(key))
    qs = Order.objects.filter(order_no__in=s_all,
                              status__nin=[STATUS_GIVE_BACK, STATUS_ISSUE_SUCC, STATUS_ISSUE_FAIL, STATUS_LOCK_FAIL],
                              yc_status__ne=YC_STATUS_ING)
    s_not_issued = set(qs.distinct("order_no"))
    s_issued = s_all-s_not_issued
    if s_issued:
        rds.srem(key, *list(s_issued))
    return qs
