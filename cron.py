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
from app.constants import ADMINS
from flask import json
from app import setup_app


app = setup_app('local', 'api')


path = os.path.dirname(__file__)
sys.path.append(os.path.join(path, ".."))


def check(func):
    def temp(*args, **kwargs):
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


def main():
    """ 定时任务处理 """

    sched = Scheduler(daemonic=False)
    sched.add_cron_job(bus_crawl, hour=15, minute=6, args=['scqcp'])
    sched.add_cron_job(bus_crawl, hour=15, minute=7, args=['gx84100'])

    sched.add_cron_job(sync_crawl_to_api, hour=15, minute=8, args=['scqcp'])
    sched.add_cron_job(sync_crawl_to_api, hour=15, minute=9, args=['gx84100'])
    sched.start()
main()    
# bus_crawl('gx84100')