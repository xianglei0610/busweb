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
from lxml import etree

from apscheduler.scheduler import Scheduler


from manage import migrate_from_crawl
from app.email import send_email
from app.constants import ADMINS, STATUS_WAITING_ISSUE
from app import setup_app
from app.models import Order, Bus100Rebot


app = setup_app(os.getenv('FLASK_CONFIG') or 'local',
                os.getenv('FLASK_SERVER') or 'api')

print app.config["DEBUG"]

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
def bus_crawl(crawl_source, province_id = None):
    if os.getenv('FLASK_CONFIG') == 'dev':
        url = "http://192.168.1.202:6800/schedule.json"
    elif os.getenv('FLASK_CONFIG') == 'prod':
        url = "http://localhost:6800/schedule.json"
    else:
        return
    data = {
          "project": "BusCrawl",
          "spider": crawl_source,
          }
    if province_id:
        data.update(province_id=province_id)
    print url
    res = requests.post(url, data=data)
    res = res.json()
    print res
    if not app.config["DEBUG"]:
        with app.app_context():
            subject = str(datetime.datetime.now())[0:19] + ' start bus_crawl,crawl_source :%s,province_id:%s ' % (crawl_source,province_id)
            sender = 'dg@12308.com'
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
    if not app.config["DEBUG"]:
        with app.app_context():
            subject = str(datetime.datetime.now())[0:19] + '  start sync_crawl_to_api,crawl_source :%s ' % crawl_source
            sender = 'dg@12308.com'
            recipients = ADMINS
            text_body = ''
            html_body = subject + '</br>' + 'logstr:%s' % logstr
            send_email(subject, sender, recipients, text_body, html_body)


@check
def polling_order_status():
    orderObj = Order.objects.filter(status=STATUS_WAITING_ISSUE)
    for order in orderObj:
        order.refresh_status()


def check_login_status(crawl_source):
    if crawl_source == 'bus100':
        obj = Bus100Rebot.objects.all()
        count = obj.count()
        url = "http://www.84100.com/user.shtml"
        phone_list = []
        for i in obj:
            print i.telephone
            res = requests.post(url, cookies=i.cookies)
            res = res.content
            sel = etree.HTML(res)
            userinfo = sel.xpath('//div[@class="c_content"]/div/ul/li[@class="myOrder"]')
            print userinfo
            if not userinfo:
                i.is_active = False
                i.save()
                phone_list.append(i.telephone)
        if not app.config["DEBUG"] and len(phone_list) == count:
            with app.app_context():
                subject = 'check_login_status'
                content = ' check_login_status,crawl_source :%s ' % crawl_source
                sender = 'dg@12308.com'
                recipients = ADMINS
                text_body = ''
                html_body = content + ' '+','.join(phone_list)
                send_email(subject, sender, recipients, text_body, html_body)


def main():
    """ 定时任务处理 """

    sched = Scheduler(daemonic=False)

    #sched.add_cron_job(bus_crawl, hour=19, minute=10, args=['scqcp'])
    #sched.add_cron_job(bus_crawl, hour=19, minute=10, args=['bus100', "450000"])
    #sched.add_cron_job(bus_crawl, hour=20, minute=40, args=['bus100', "370000"])
    #sched.add_cron_job(bus_crawl, hour=22, minute=10, args=['bus100', "210000"])
    sched.add_cron_job(sync_crawl_to_api, hour=23, minute=50, args=['bus100'])

    sched.add_interval_job(check_login_status, minutes=5, args=['bus100'])
#     sched.add_interval_job(polling_order_status, minutes=1)

    sched.start()


if __name__ == '__main__':
    main()
    #check_login_status('bus100')
    #bus_crawl('bus100')
