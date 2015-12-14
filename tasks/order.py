# -*- coding:utf-8 -*-
import urllib2
import json
import datetime

from app.constants import *
from app import celery
from app.models import Order


@celery.task
def check_order_expire(order_no):
    order = Order.objects.get(order_no=order_no)
