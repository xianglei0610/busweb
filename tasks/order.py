# -*- coding:utf-8 -*-
import urllib2
import json
import datetime
import random

from app.constants import *
from app import celery
from app.utils import getRedisObj


@celery.task(bind=True, ignore_result=True)
def check_order_expire(self, order_no):
    """
    定时检查订单过期情况
    """
    from app.models import Order
    order = Order.objects.get(order_no=order_no)
    if order.status != STATUS_WAITING_ISSUE:
        return
    try:
        order.refresh_issued()
    except Exception, e:
        print e
    if order.status == STATUS_WAITING_ISSUE:
        self.retry(countdown=10, max_retries=30)


@celery.task(bind=True, ignore_result=True)
def refresh_kefu_order(self, username, order_no):
    """
    刷新客服订单状态
    """
    from app.models import Order, AdminUser
    order = Order.objects.get(order_no=order_no)
    user = AdminUser.objects.get(username=username)
    if order.status != STATUS_WAITING_ISSUE:
        return
    try:
        order.refresh_issued()
    except Exception, e:
        print e
    if order.status == STATUS_WAITING_ISSUE:
        self.retry(countdown=3+random.random()*10%3, max_retries=100)
