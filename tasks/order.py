# -*- coding:utf-8 -*-
import random
import datetime
import urllib2
import json

from app.constants import *
from app import celery
from app.utils import getRedisObj
from app.email import send_email
from app.flow import get_flow
from app.models import Order
from app import order_log
from flask import current_app


@celery.task(bind=True, ignore_result=True)
def async_refresh_order(self, order_no, retry_seq=1):
    """
    定时刷新订单状态
    """
    order_log.info("[async_refresh_order] order:%s retry_seq: %s", order_no, retry_seq)
    order = Order.objects.get(order_no=order_no)
    status = order.status
    if order.crawl_source == SOURCE_FB:
        return
    if status not in [STATUS_ISSUE_ING, STATUS_WAITING_ISSUE]:
        return

    flow = get_flow(order.crawl_source)
    try:
        flow.refresh_issue(order)
    finally:
        if status == STATUS_WAITING_ISSUE:
            if retry_seq < 100:
                seconds = random.randint(3, 5)
            elif retry_seq < 200:
                seconds = random.randint(10, 20)
            else:
                seconds = random.randint(60, 90)
        else:
            if retry_seq < 100:
                seconds = random.randint(10, 15)
            else:
                seconds = random.randint(90, 120)
        self.retry(kwargs={"retry_seq": retry_seq+1}, countdown=seconds, max_retries=60*12)


@celery.task(bind=True, ignore_result=True)
def issue_fail_send_email(self, key):
    """
    连续3个单失败就发送邮件
    """
    r = getRedisObj()
    order_nos = r.smembers(key)
    order_nos = ','.join(list(order_nos))
    if not current_app.config['DEBUG']:
        subject = '连续3个单失败'
        sender = 'dg@12308.com'
        recipients = ADMINS
        text_body = ''
        html_body = subject + '</br>' + 'order :%s error' % order_nos
        send_email(subject, sender, recipients, text_body, html_body)


@celery.task(bind=True, ignore_result=True)
def check_order_completed(self, username, key, order_no, is_send=False):
    """
    订单有效期只有5分钟
    """
    from app.models import Order
    r = getRedisObj()
    flag = r.sismember(key, order_no)
    orderObj = Order.objects.get(order_no=order_no)
    now = datetime.datetime.now()
    if not current_app.config['DEBUG']:
        if flag and not is_send:
            try:
                if (orderObj.lock_info['expire_datetime']-now).total_seconds() < 300:
                    subject = "订单有效期只有5分钟了"
                    content = '%s,%s,订单快到有效期,下单时间:%s,12308订单号:%s' % (username, order_no, orderObj.create_date_time,orderObj.out_order_no)
                    sender = 'dg@12308.com'
                    recipients = ADMINS
                    text_body = ''
                    html_body = content
                    send_email(subject, sender, recipients, text_body, html_body)
                    is_send = True
            except:
                pass
        if orderObj.status == STATUS_WAITING_ISSUE:
            self.retry(kwargs={"is_send": is_send},countdown=30+random.random()*10%3, max_retries=200)


@celery.task(bind=True, ignore_result=True)
def async_lock_ticket(self, order_no, retry_seq=1):
    """
    请求源网站锁票 + 锁票成功回调

    Return:
        expire_time: "2015-11-11 11:11:11",     # 订单过期时间
        total_price: 322，          # 车票价格
    """
    order_log.info("[async_lock_ticket] order:%s retry_seq: %s", order_no, retry_seq)
    order = Order.objects.get(order_no=order_no)
    if order.status != STATUS_WAITING_LOCK:
        return
    flow = get_flow(order.crawl_source)
    try:
        flow.lock_ticket(order)
    except Exception, e:
        order_log.exception("async_lock_ticket")
        self.retry(kwargs={"retry_seq": retry_seq+1}, countdown=20, max_retries=10)


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
        if not order.pick_code_list:    # 没取票信息不回调
            order_log.info("[issue-callback-ignore] no pick info")
            return
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
    elif order.status in [STATUS_GIVE_BACK, STATUS_LOCK_FAIL, STATUS_ISSUE_FAIL]:
        ret = {
            "code": RET_ISSUED_FAIL,
            "message": "fail",
            "data": {
                "sys_order_no": order.order_no,
                "out_order_no": order.out_order_no,
                "raw_order_no": order.raw_order_no,
            }
        }
    else:
        order_log.info("[issue-callback-ignore] status incorrect")
        return
    order_log.info("[issue-callback] %s %s", order_no, str(ret))
    response = urllib2.urlopen(cb_url, json.dumps(ret), timeout=10)
    order_log.info("[issue-callback-response]%s %s", order_no, str(response))
