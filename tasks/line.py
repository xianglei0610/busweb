#!/usr/bin/env python
# encoding: utf-8
from app.constants import *
from app import celery
from app.email import send_email
from flask import current_app


@celery.task(bind=True, ignore_result=True)
def refresh_station_order(self):
    """
    刷新车站今日订单数和成功率
    """
    from app.models import Order


@celery.task(bind=True, ignore_result=True)
def refresh_station_line(self):
    """
    刷新车站线路数
    """
    from app.models import Line
    for d in Line.objects.aggregate({"$group":{"_id":{"sta_name":"$s_sta_name", "city_name": "$s_city_name"}, "cnt":{"$sum":1}}}):
        pass
