#!/usr/bin/env python
# -*- coding:utf-8 *-*
'''
计划任务配置
'''
import os
import sys
import requests
import traceback
import datetime
import time

from apscheduler.scheduler import Scheduler


from manage import migrate_from_crawl
from app.email import send_email
from app.constants import ADMINS, STATUS_WAITING_ISSUE
from app import setup_app
from app.models import Order


app = setup_app('local', 'api')


path = os.path.dirname(__file__)
sys.path.append(os.path.join(path, ".."))


def check(func):
    def temp(*args, **kwargs):
        print args
        if args == ():
            key = func.__name__ + str(datetime.datetime.now())[0:10]
        else:
            key = str(args[0]) + func.__name__ + str(datetime.datetime.now())[0:10]
        pid = os.path.join(path, key+'.txt')
        print pid
        if os.path.exists(pid):
            return
        else:
            os.system("touch %s"%pid)
        try:
            start = time.time()
            print "---------------- start %s  at %s ---------------"%(func.__name__,str(datetime.datetime.now()))
            func(*args, **kwargs)
            print "---------------- done %s at %s ---------------"%(func.__name__,str(datetime.datetime.now()))
            end = time.time()
            logstr = "%s ,%sspend %s" % (func.__name__, args, end - start)
            print logstr

        except:
            print traceback.format_exc()
        os.system("rm %s"%pid)
    return temp


@check
def bus_crawl(crawl_source):
    url = "http://192.168.1.202:6800/schedule.json"
    data = {
          "project": "BusCrawl",
          "spider": crawl_source
          }
    print data
    res = requests.post(url, data=data)
    res = res.json()
    with app.app_context():
        subject = str(datetime.datetime.now())[0:19] + '  start bus_crawl,crawl_source :%s ' % crawl_source
        sender = 'xiangleilei@12308.com'
        recipients = ADMINS
        text_body = ''
        html_body = subject + '</br>' + 'result:%s' % res
        send_email(subject, sender, recipients, text_body, html_body)


@check
def sync_crawl_to_api(crawl_source):
    start = time.time()
    migrate_from_crawl(crawl_source)
    end = time.time()
    logstr = "sync_crawl_to_api ,%s spend %s" % (crawl_source, end - start)
    print logstr
    with app.app_context():
        subject = str(datetime.datetime.now())[0:19] + '  start sync_crawl_to_api,crawl_source :%s ' % crawl_source
        sender = 'xiangleilei@12308.com'
        recipients = ADMINS
        text_body = ''
        html_body = subject + '</br>' + 'logstr:%s' % logstr
        send_email(subject, sender, recipients, text_body, html_body)


@check
def polling_order_status():
    orderObj = Order.objects.filter(status=STATUS_WAITING_ISSUE)
    for order in orderObj:
        order.refresh_status()

from app.utils import getRedisObj

def reflesh_order_list():
#     user_id = request.args.get("user_id")
#     status = request.args.get("status", 0)
    user_id = 1
    status = 0
    KF_ORDER_CT = 3
    if not status:
        r = getRedisObj()
        key = 'order_list:%s' % user_id
        order_ct = r.scard(key)
        print order_ct
        if order_ct < KF_ORDER_CT:
            count = KF_ORDER_CT-order_ct
            lock_order_list = r.zrange('lock_order_list', 0, count-1)
            for i in lock_order_list:
                r.sadd(key, i)
                r.zrem('lock_order_list', i)



def main():
    """ 定时任务处理 """

    sched = Scheduler(daemonic=False)
    sched.add_cron_job(bus_crawl, hour=10, minute=53, args=['scqcp'])
    sched.add_cron_job(bus_crawl, hour=10, minute=52, args=['bus100'])

    sched.add_cron_job(sync_crawl_to_api, hour=4, minute=30, args=['scqcp'])
    sched.add_cron_job(sync_crawl_to_api, hour=6, minute=30, args=['bus100'])

#     sched.add_interval_job(polling_order_status, minutes=1)

    sched.start()


if __name__ == '__main__':
    reflesh_order_list()
#     polling_order_status()
# bus_crawl('bus100')