#!/usr/bin/env python
# encoding: utf-8

from app.constants import *
from app.utils import get_redis
from app.models import Order
from datetime import datetime as dte


def enqueue_wating_lock(order):
    """
    等待下单队列
    """
    rds = get_redis("order")
    rds.lpush(RK_WATING_LOCK_ORDERS, order.order_no)


def dequeue_wating_lock(username=""):
    rds = get_redis("order")
    no = rds.rpop(RK_WATING_LOCK_ORDERS)
    if not no:
        return None
    order = Order.objects.get(order_no=no)
    if order.crawl_source in [SOURCE_SCQCP, SOURCE_CBD]:
        today = dte.now().strftime("%Y-%m-%d")
        orderct = Order.objects.filter(crawl_source=order.crawl_source,
                                       create_date_time__gt=today,
                                       kefu_username=username,
                                       status__in=[STATUS_WAITING_ISSUE, STATUS_ISSUE_ING]).count()
        if orderct > 0:
            rds.lpush(RK_WATING_LOCK_ORDERS, order.order_no)
            return None
    if order.crawl_source == SOURCE_CBD and username not in ["luocky", "liuquan"]:
        rds.lpush(RK_WATING_LOCK_ORDERS, order.order_no)
        return None
    return order


def wating_lock_size():
    rds = get_redis("order")
    return rds.llen(RK_WATING_LOCK_ORDERS)


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


def deal_kefu_order(order, user):
    flag = True
    if ASSIGN_FLAG:
        for k, v in ASSIGN_ACCOUNT.items():
            if order.crawl_source in v and user.username != k:
                enqueue_wating_lock(order)
                return False
            if user.username == k and order.crawl_source not in v:
                return False
        return flag
    else:
        return flag