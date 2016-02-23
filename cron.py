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


from manage import del_source_people
from app.email import send_email
from app.constants import ADMINS, STATUS_WAITING_ISSUE
from app import setup_app
from app.models import Order, Bus100Rebot, BabaWebRebot
#from sms import send_msg
from app.constants import sms_phone_list


app = setup_app()

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
def bus_crawl(crawl_source, province_id = None, crawl_kwargs={}):
    if os.getenv('FLASK_CONFIG') == 'dev':
        url = "http://192.168.1.202:6800/schedule.json"
    elif os.getenv('FLASK_CONFIG') == 'prod':
        url = "http://localhost:6800/schedule.json"
        # url = "http://120.27.150.94:6800/schedule.json"
    else:
        return
    data = {
          "project": "BusCrawl",
          "spider": crawl_source,
          }
    if province_id:
        data.update(province_id=province_id)
    data.update(crawl_kwargs)
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


def del_people(crawl_source):
    del_source_people(crawl_source)
    for rebot in BabaWebRebot.objects.all():
        rebot.clear_riders()


def main():
    """ 定时任务处理 """

    sched = Scheduler(daemonic=False)

    # 巴士壹佰
    sched.add_cron_job(bus_crawl, hour=12, minute=10, args=['bus100', "450000"]) #广西
    sched.add_cron_job(bus_crawl, hour=18, minute=20, args=['bus100', "370000"]) #山东
    sched.add_cron_job(bus_crawl, hour=20, minute=10, args=['bus100', "410000"]) #河南

    # 巴巴快巴
    sched.add_cron_job(bus_crawl, hour=21, minute=10, args=['baba'])

    # 方便网
    sched.add_cron_job(bus_crawl, hour=23, minute=0, args=['fangbian'], kwargs={"crawl_kwargs":{"province": "山东"}})
    sched.add_cron_job(bus_crawl, hour=23, minute=0, args=['fangbian'], kwargs={"crawl_kwargs":{"province": "河南"}})
    sched.add_cron_job(bus_crawl, hour=23, minute=0, args=['fangbian'], kwargs={"crawl_kwargs":{"province": "广西"}})


    # 其他
    sched.add_cron_job(del_people, hour=22, minute=40, args=['bus100']) #删除源站常用联系人

    sched.start()


if __name__ == '__main__':
    main()
#     check_login_status('bus100')
    #bus_crawl('bus100')
    #del_people('bus100')
