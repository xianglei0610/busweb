#!/usr/bin/env python
# encoding: utf-8
import time

from app.constants import *
from app.utils import get_redis
from app.models import Order
from datetime import datetime as dte


def enqueue_wating_lock(order, score=0, is_first=True):
    """
    等待下单队列
    """
    now = dte.now()
    line = order.line
    rds = get_redis("order")

    if is_first:
        if (line.drv_datetime-now).total_seconds() <= 3*60*60+20:       # 3个小时内的车优先处理
            rds.zadd(RK_WATING_LOCK_ORDERS, order.order_no, 0)
        else:
            rds.zadd(RK_WATING_LOCK_ORDERS, order.order_no, int(time.time()))
    else:
        rds.zadd(RK_WATING_LOCK_ORDERS, order.order_no, min(int(time.time()), score+1))


def dequeue_wating_lock(user):
    rds = get_redis("order")
    lst = rds.zrange(RK_WATING_LOCK_ORDERS, 0, 0, withscores=True)
    if not lst:
        return None
    no, score = lst[0]
    rds.zrem(RK_WATING_LOCK_ORDERS, no)
    order = Order.objects.get(order_no=no)
    for ptype in user.source_include:
        if order.crawl_source in PAY_TYPE_SOURCE[ptype]:
            return order
    enqueue_wating_lock(order, is_first=False, score=score)
    return None


def waiting_lock_size():
    rds = get_redis("order")
    return rds.llen(RK_WATING_LOCK_ORDERS) + rds.llen(RK_WATING_LOCK_ORDERS2)


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
                              status__nin=[STATUS_GIVE_BACK, STATUS_ISSUE_SUCC, STATUS_ISSUE_FAIL, STATUS_LOCK_FAIL])
    s_not_issued = set(qs.distinct("order_no"))
    s_issued = s_all-s_not_issued
    if s_issued:
        rds.srem(key, *list(s_issued))
    return qs
