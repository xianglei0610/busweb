#!/usr/bin/env python
# -*- coding:utf-8 *-*
'''
计划任务配置
'''
import requests
import traceback
import time
import json

from app.constants import *
from apscheduler.scheduler import Scheduler
from datetime import datetime as dte
from app.email import send_email
from app.constants import ADMINS
from app import setup_app
from app import cron_log
from app.utils import get_redis


app = setup_app()


def check(func):
    def temp(*args, **kwargs):
        res = None
        try:
            t1 = time.time()
            with app.app_context():
                res = func(*args, **kwargs)
            cost = time.time() - t1
            cron_log.info("[succss] %s %s %s, return: %s, cost time: %s", func.__name__, args, kwargs, res, cost)
        except:
            cron_log.error("%s,%s,%s", traceback.format_exc(), args, kwargs)
        return res
    return temp


@check
def bus_crawl(crawl_source, province_id = None, crawl_kwargs={}):
    url_list = app.config["SCRAPYD_URLS"]
    data = {
          "project": "BusCrawl",
          "spider": crawl_source,
    }
    if province_id:
        data.update(province_id=province_id)
    data.update(crawl_kwargs)

    res_lst = []
    for url in url_list:
        res = requests.post(url, data=data)
        res_lst.append("%s: %s" % (url, res.content))

    subject = "bus_crawl(%s, province_id=%s, crawl_kwargs=%s) " % (crawl_source, province_id, json.dumps(crawl_kwargs, ensure_ascii=False))
    html_body = subject + '</br>' + 'result:</br>%s' % "</br>".join(res_lst)
    send_email(subject,
            app.config["MAIL_USERNAME"],
            ADMINS,
            "",
            html_body)


@check
def delete_source_riders():
    """
    删除源站乘客信息
    """
    from app.models import get_rebot_class
    for source in SOURCE_INFO.keys():
        for rebot_cls in get_rebot_class(source):
            if not hasattr(rebot_cls, "clear_riders"):
                continue
            for rebot in rebot_cls.objects.all():
                rebot.clear_riders()


@check
def clear_lines():
    """
    清理过期线路数据
    """
    from app.models import Line
    today = dte.now().strftime("%Y-%m-%d")
    cnt = Line.objects.filter(drv_date__lt=today).delete()
    return "%s line deleted" % cnt


@check
def clear_redis_data():
    """
    清理redis数据
    """
    r = get_redis("default")
    now = time.time()
    result = {}
    for k in r.keys("line:done:*"):
        result[k] = 0
        for sk, v in r.hgetall(k).items():
            if now-float(v) > 12*60*60:
                r.hdel(k, sk)
                result[k] += 1
    return result


def main():
    """ 定时任务处理 """

    sched = Scheduler(daemonic=False)

    # 巴士壹佰
    sched.add_cron_job(bus_crawl, hour=12, minute=10, args=['bus100', "450000"]) #广西
    sched.add_cron_job(bus_crawl, hour=18, minute=20, args=['bus100', "370000"]) #山东
    sched.add_cron_job(bus_crawl, hour=19, minute=40, args=['bus100', "410000"]) #河南

    # 巴巴快巴
    sched.add_cron_job(bus_crawl, hour=21, minute=10, args=['baba'])

    # 方便网
    sched.add_cron_job(bus_crawl, hour=23, minute=0, args=['fangbian'], kwargs={"crawl_kwargs":{"province": "山东"}})
    sched.add_cron_job(bus_crawl, hour=23, minute=0, args=['fangbian'], kwargs={"crawl_kwargs":{"province": "河南"}})
    sched.add_cron_job(bus_crawl, hour=23, minute=0, args=['fangbian'], kwargs={"crawl_kwargs":{"province": "广西"}})
    sched.add_cron_job(bus_crawl, hour=22, minute=0, args=['fangbian'], kwargs={"crawl_kwargs":{"city": "苏州"}})
    sched.add_cron_job(bus_crawl, hour=21, minute=10, args=['fangbian'], kwargs={"crawl_kwargs":{"city": "南京"}})
    sched.add_cron_job(bus_crawl, hour=0, minute=10, args=['fangbian'], kwargs={"crawl_kwargs":{"city": "重庆"}})

    # 贵州汽车票务网
    sched.add_cron_job(bus_crawl, hour=6, minute=10, args=['gzqcp'])

    # 重庆客运
    sched.add_cron_job(bus_crawl, hour=0, minute=10, args=['cqky'])

    # 江苏客运
    sched.add_cron_job(bus_crawl, hour=22, minute=0, args=['jsky'], kwargs={"crawl_kwargs":{"city": "苏州"}})
    sched.add_cron_job(bus_crawl, hour=21, minute=10, args=['jsky'], kwargs={"crawl_kwargs":{"city": "南京"}})

    # 车巴达
    sched.add_cron_job(bus_crawl, hour=22, minute=0, args=['cbd'], kwargs={"crawl_kwargs":{"city": "苏州"}})
    sched.add_cron_job(bus_crawl, hour=21, minute=10, args=['cbd'], kwargs={"crawl_kwargs":{"city": "南京"}})


    # 快巴
    sched.add_cron_job(bus_crawl, hour=20, minute=30, args=['kuaiba'], kwargs={"crawl_kwargs":{"province": "北京"}})

    # 其他
    sched.add_cron_job(delete_source_riders, hour=22, minute=40)
    sched.add_cron_job(clear_lines, hour=1, minute=0)
    sched.add_cron_job(clear_redis_data, hour=5, minute=0)

    sched.start()

if __name__ == '__main__':
    main()
    #clear_redis_data()
    #bus_crawl('bus100', crawl_kwargs={"province": "四川"})
    #delete_source_riders()
    #clear_lines()
