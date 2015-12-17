# -*- coding:utf-8 -*-
import urllib2
import json
import datetime

from app.constants import *
from app import celery


@celery.task(bind=True)
def check_order_expire(self, order_no):
    from app.models import Order
    order = Order.objects.get(order_no=order_no)
    if order.status != STATUS_WAITING_ISSUE:
        return
    order.refresh_issued()
    if order.status == STATUS_WAITING_ISSUE:
        self.retry(countdown=20)
