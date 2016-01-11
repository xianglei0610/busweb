# -*- coding:utf-8 -*-
import random

from app.constants import *
from app import celery
from app.utils import getRedisObj
from app.email import send_email
from app.flow import get_flow
from app.models import Order
from app import order_log


@celery.task(bind=True, ignore_result=True)
def check_order_expire(self, order_no):
    """
    定时检查订单过期情况
    """
    order_log.info("[check_order_expire] order:%s", order_no)
    order = Order.objects.get(order_no=order_no)
    if order.status != STATUS_WAITING_ISSUE:
        return
    flow = get_flow(order.crawl_source)
    flow.refresh_issue(order)
    if order.status == STATUS_WAITING_ISSUE:
        self.retry(countdown=30, max_retries=30)


@celery.task(bind=True, ignore_result=True)
def refresh_kefu_order(self, username, order_no):
    """
    刷新客服订单状态
    """
    order_log.info("[refresh_kefu_order] order:%s, kefu:%s", order_no, username)
    order = Order.objects.get(order_no=order_no)
    if order.status not in (STATUS_WAITING_ISSUE, STATUS_ISSUE_ING):
        return
    flow = get_flow(order.crawl_source)
    flow.refresh_issue(order)
    if order.status == STATUS_WAITING_ISSUE:
        self.retry(countdown=3+random.random()*10%3, max_retries=200)


@celery.task(bind=True, ignore_result=True)
def refresh_issueing_order(self, order_no, retry_seq=1):
    """
    刷新正在出票订单状态
    """
    order_log.info("[refresh_issueing_order] order:%s retry_seq: %s", order_no, retry_seq)
    order = Order.objects.get(order_no=order_no)
    if order.status != STATUS_ISSUE_ING:
        return
    flow = get_flow(order.crawl_source)
    flow.refresh_issue(order)
    if order.status == STATUS_ISSUE_ING:
        if retry_seq < 30:      # 前40次,每3~5s刷新一次
            seconds = random.randint(3, 5)
        elif retry_seq < 100:   # 前40~100次
            seconds = random.randint(30, 40)
        else:
            seconds = random.randint(60, 90)
        self.retry(kwargs={"retry_seq": retry_seq+1}, countdown=seconds, max_retries=60*12)


@celery.task(bind=True, ignore_result=True)
def issue_fail_send_email(self, key):
    """
    连续3个单失败就发送邮件
    """
    r = getRedisObj()
    order_nos = r.smembers(key)
    order_nos = ','.join(list(order_nos))
    subject = '连续3个单失败'
    sender = 'dg@12308.com'
    recipients = ADMINS
    text_body = ''
    html_body = subject + '</br>' + 'order :%s error' % order_nos
    send_email(subject, sender, recipients, text_body, html_body)


@celery.task(bind=True, ignore_result=True)
def check_order_completed(self, username, key, order_no):
    """
    超过三分钟订单未处理
    """
    from app.models import Order
    r = getRedisObj()
    flag = r.sismember(key, order_no)
    orderObj = Order.objects.get(order_no=order_no)
    if flag:
        subject = "超过三分钟有未处理订单"
        content = '%s,超过三分钟有未处理订单:%s,下单时间:%s,12308订单号:%s' % (username, order_no, orderObj.create_date_time,orderObj.out_order_no)
        sender = 'dg@12308.com'
        recipients = ADMINS
        text_body = ''
        html_body = content
        send_email(subject, sender, recipients, text_body, html_body)
