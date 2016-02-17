#!/usr/bin/env python
# encoding: utf-8

from app.constants import *
from app.utils import get_redis
from app.models import Order


def enqueue_wating_lock(order):
    """
    等待下单队列
    """
    rds = get_redis("order")
    rds.lpush(RK_WATING_LOCK_ORDERS, order.order_no)


def dequeue_wating_lock():
    rds = get_redis("order")
    no = rds.rpop(RK_WATING_LOCK_ORDERS)
    if not no:
        return None
    return Order.objects.get(order_no=no)


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
    return Order.objects.filter(order_no__in=rds.smembers(key))
