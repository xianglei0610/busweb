#!/usr/bin/env python
# -*- coding:utf-8 *-*
'''
计划任务配置
'''
import requests
import traceback
import time

from app.constants import *
from apscheduler.scheduler import Scheduler
from datetime import datetime as dte
# from app.email import send_email
# from app.constants import ADMINS
from app import setup_app
from app import cron_log
from app.utils import get_redis


app = setup_app()


def check(run_in_local=False):
    """
    run_in_local 是否允许在local环境运行
    """
    def wrap(func):
        def sub_wrap(*args, **kwargs):
            res = None
            try:
                if not run_in_local and app.config["DEBUG"]:
                    cron_log.info("[ignore] forbid run at debug mode")
                    return None
                t1 = time.time()
                #cron_log.info("[start] %s %s %s", func.__name__, args, kwargs)
                with app.app_context():
                    res = func(*args, **kwargs)
                cost = time.time() - t1
                cron_log.info("[succss] %s %s %s, return: %s, cost time: %s", func.__name__, args, kwargs, res, cost)
            except:
                cron_log.error("%s,%s,%s", traceback.format_exc(), args, kwargs)
            return res
        return sub_wrap
    return wrap


@check()
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

    # subject = "bus_crawl(%s, province_id=%s, crawl_kwargs=%s) " % (crawl_source, province_id, json.dumps(crawl_kwargs, ensure_ascii=False))
    # html_body = subject + '</br>' + 'result:</br>%s' % "</br>".join(res_lst)
    # send_email(subject,
    #         app.config["MAIL_USERNAME"],
    #         ADMINS,
    #         "",
    #         html_body)


@check()
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


@check(run_in_local=True)
def clear_lines():
    """
    清理过期线路数据
    """
    from app.models import Line
    today = dte.now().strftime("%Y-%m-%d")
    cnt = Line.objects.filter(drv_date__lt=today).delete()
    return "%s line deleted" % cnt


@check(run_in_local=True)
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


@check(run_in_local=True)
def crawl_proxy_haodaili():
    from app.proxy import proxy_producer
    data = {}
    cnt = proxy_producer.crawl_from_haodaili()
    data["haodaili"] = cnt
    return data

@check(run_in_local=True)
def crawl_proxy_samair():
    from app.proxy import proxy_producer
    data = {}
    cnt = proxy_producer.crawl_from_samair()
    data["samair"] = cnt
    return data


@check(run_in_local=True)
def crawl_proxy_66ip():
    from app.proxy import proxy_producer
    data = {}
    cnt = proxy_producer.crawl_from_66ip()
    data["66ip"] = cnt
    return data

@check(run_in_local=True)
def crawl_proxy_xici():
    from app.proxy import proxy_producer
    data = {}
    cnt = proxy_producer.crawl_from_xici()
    data["xici"] = cnt
    return data

@check(run_in_local=True)
def crawl_proxy_zdaye():
    from app.proxy import proxy_producer
    data = {}
    cnt = proxy_producer.crawl_from_zdaye()
    data["zdaye"] = cnt
    return data

@check(run_in_local=True)
def check_proxy():
    from app.proxy import proxy_producer
    for ipstr in proxy_producer.all_proxy():
        if not proxy_producer.valid_proxy(ipstr):
            proxy_producer.remove_proxy(ipstr)
    return proxy_producer.proxy_size()


@check(run_in_local=True)
def check_proxy_cqky():
    from app.proxy import cqky_proxy
    for ipstr in cqky_proxy.all_proxy():
        if not cqky_proxy.valid_proxy(ipstr):
            cqky_proxy.remove_proxy(ipstr)
    return cqky_proxy.proxy_size()


@check(run_in_local=True)
def check_proxy_tc():
    from app.proxy import tc_proxy as con
    for ipstr in con.all_proxy():
        if not con.valid_proxy(ipstr):
            con.remove_proxy(ipstr)
    return con.proxy_size()


@check(run_in_local=True)
def check_proxy_scqcp():
    from app.proxy import scqcp_proxy as con
    for ipstr in con.all_proxy():
        if not con.valid_proxy(ipstr):
            con.remove_proxy(ipstr)
    return con.proxy_size()


@check(run_in_local=True)
def check_proxy_cbd():
    from app.proxy import cbd_proxy as con
    for ipstr in con.all_proxy():
        if not con.valid_proxy(ipstr):
            con.remove_proxy(ipstr)
    return con.proxy_size()


@check(run_in_local=True)
def check_proxy_bjky():
    from app.proxy import bjky_proxy as con
    for ipstr in con.all_proxy():
        if not con.valid_proxy(ipstr):
            con.remove_proxy(ipstr)
    return con.proxy_size()


@check(run_in_local=True)
def check_proxy_lnky():
    from app.proxy import lnky_proxy as con
    for ipstr in con.all_proxy():
        if not con.valid_proxy(ipstr):
            con.remove_proxy(ipstr)
    return con.proxy_size()


@check(run_in_local=True)
def check_proxy_e8s():
    from app.proxy import e8s_proxy as con
    for ipstr in con.all_proxy():
        if not con.valid_proxy(ipstr):
            con.remove_proxy(ipstr)
    return con.proxy_size()


@check(run_in_local=True)
def check_proxy_changtu():
    from app.proxy import changtu_proxy as con
    for ipstr in con.all_proxy():
        if not con.valid_proxy(ipstr):
            con.remove_proxy(ipstr)
    return con.proxy_size()


def main():
    sched = Scheduler(daemonic=False)

    # 巴士壹佰
    #sched.add_cron_job(bus_crawl, hour=12, minute=10, args=['bus100', "450000"]) #广西
    #sched.add_cron_job(bus_crawl, hour=18, minute=20, args=['bus100', "370000"]) #山东
    #sched.add_cron_job(bus_crawl, hour=19, minute=40, args=['bus100', "410000"]) #河南

    # 巴巴快巴
    sched.add_cron_job(bus_crawl, hour=20, minute=10, args=['baba'])

    # 方便网
    sched.add_cron_job(bus_crawl, hour=1, minute=0, args=['fangbian'], kwargs={"crawl_kwargs":{"province": "山东"}})
    #sched.add_cron_job(bus_crawl, hour=23, minute=0, args=['fangbian'], kwargs={"crawl_kwargs":{"province": "河南"}})
    #sched.add_cron_job(bus_crawl, hour=23, minute=0, args=['fangbian'], kwargs={"crawl_kwargs":{"province": "广西"}})
    sched.add_cron_job(bus_crawl, hour=2, minute=0, args=['fangbian'], kwargs={"crawl_kwargs":{"city": "苏州,张家港"}})
    sched.add_cron_job(bus_crawl, hour=2, minute=0, args=['fangbian'], kwargs={"crawl_kwargs":{"city": "昆山,太仓"}})
    sched.add_cron_job(bus_crawl, hour=2, minute=0, args=['fangbian'], kwargs={"crawl_kwargs":{"city": "常熟,吴江"}})
    sched.add_cron_job(bus_crawl, hour=3, minute=10, args=['fangbian'], kwargs={"crawl_kwargs":{"city": "南京"}})
    sched.add_cron_job(bus_crawl, hour=3, minute=5, args=['fangbian'], kwargs={"crawl_kwargs":{"city": "无锡"}})
    sched.add_cron_job(bus_crawl, hour=3, minute=10, args=['fangbian'], kwargs={"crawl_kwargs":{"city": "常州"}})
    sched.add_cron_job(bus_crawl, hour=4, minute=30, args=['fangbian'], kwargs={"crawl_kwargs":{"city": "重庆"}})
    sched.add_cron_job(bus_crawl, hour=4, minute=10, args=['fangbian'], kwargs={"crawl_kwargs":{"province": "四川"}})
    sched.add_cron_job(bus_crawl, hour=5, minute=10, args=['fangbian'], kwargs={"crawl_kwargs":{"province": "南通"}})

    # 贵州汽车票务网
#     sched.add_cron_job(bus_crawl, hour=6, minute=10, args=['gzqcp'])

    # 重庆客运
    sched.add_cron_job(bus_crawl, hour=20, minute=10, args=['cqky'])

    # 四川
    sched.add_cron_job(bus_crawl, hour=22, minute=30, args=['scqcp'])
#     sched.add_cron_job(bus_crawl, hour=22, minute=30, args=['scqcp'], kwargs={"crawl_kwargs":{"city": "成都市"}})

    # 江苏道路客运
    sched.add_cron_job(bus_crawl, hour=20, minute=30, args=['jsdlky'])

    # 泰州客运
    sched.add_cron_job(bus_crawl, hour=19, minute=30, args=['tzky'])

    # 畅途网
    sched.add_cron_job(bus_crawl, hour=20, minute=30, args=['changtu'], kwargs={"crawl_kwargs":{"city": "南京"}})
    sched.add_cron_job(bus_crawl, hour=21, minute=30, args=['changtu'], kwargs={"crawl_kwargs":{"city": "济南"}})
    sched.add_cron_job(bus_crawl, hour=22, minute=30, args=['changtu'], kwargs={"crawl_kwargs":{"city": "淄博"}})
    sched.add_cron_job(bus_crawl, hour=23, minute=30, args=['changtu'], kwargs={"crawl_kwargs":{"city": "临沂"}})
    sched.add_cron_job(bus_crawl, hour=0, minute=0, args=['changtu'], kwargs={"crawl_kwargs":{"city": "威海"}})

    # 江苏客运
    sched.add_cron_job(bus_crawl, hour=8, minute=0, args=['jsky'], kwargs={"crawl_kwargs":{"city": "苏州,张家港"}})
    sched.add_cron_job(bus_crawl, hour=9, minute=30, args=['jsky'], kwargs={"crawl_kwargs":{"city": "江阴,宜兴"}})
    sched.add_cron_job(bus_crawl, hour=16, minute=0, args=['jsky'], kwargs={"crawl_kwargs":{"city": "宿迁"}})
    sched.add_cron_job(bus_crawl, hour=17, minute=0, args=['jsky'], kwargs={"crawl_kwargs":{"city": "徐州"}})
    sched.add_cron_job(bus_crawl, hour=18, minute=10, args=['jsky'], kwargs={"crawl_kwargs":{"city": "南京"}})
    sched.add_cron_job(bus_crawl, hour=18, minute=10, args=['jsky'], kwargs={"crawl_kwargs":{"city": "南通"}})
    sched.add_cron_job(bus_crawl, hour=19, minute=10, args=['jsky'], kwargs={"crawl_kwargs":{"city": "无锡"}})
    sched.add_cron_job(bus_crawl, hour=19, minute=10, args=['jsky'], kwargs={"crawl_kwargs":{"city": "常州"}})
    sched.add_cron_job(bus_crawl, hour=20, minute=0, args=['jsky'], kwargs={"crawl_kwargs":{"city": "昆山,太仓"}})
    sched.add_cron_job(bus_crawl, hour=20, minute=30, args=['jsky'], kwargs={"crawl_kwargs":{"city": "常熟,吴江"}})
    sched.add_cron_job(bus_crawl, hour=21, minute=30, args=['jsky'], kwargs={"crawl_kwargs":{"city": "泰州"}})

    # 车巴达
    sched.add_cron_job(bus_crawl, hour=17, minute=0, args=['cbd'], kwargs={"crawl_kwargs":{"city": "苏州, 张家港"}})
    sched.add_cron_job(bus_crawl, hour=18, minute=10, args=['cbd'], kwargs={"crawl_kwargs":{"city": "南京"}})
    sched.add_cron_job(bus_crawl, hour=18, minute=10, args=['cbd'], kwargs={"crawl_kwargs":{"city": "南通"}})
    sched.add_cron_job(bus_crawl, hour=19, minute=10, args=['cbd'], kwargs={"crawl_kwargs":{"city": "无锡"}})
    sched.add_cron_job(bus_crawl, hour=19, minute=10, args=['cbd'], kwargs={"crawl_kwargs":{"city": "常州"}})
    sched.add_cron_job(bus_crawl, hour=20, minute=30, args=['cbd'], kwargs={"crawl_kwargs":{"city": "昆山,太仓"}})
    sched.add_cron_job(bus_crawl, hour=20, minute=0, args=['cbd'], kwargs={"crawl_kwargs":{"city": "常熟,吴江"}})

    # 同程旅行
    sched.add_cron_job(bus_crawl, hour=17, minute=10, args=['tongcheng'], kwargs={"crawl_kwargs":{"city": "南京"}})
    sched.add_cron_job(bus_crawl, hour=18, minute=10, args=['tongcheng'], kwargs={"crawl_kwargs":{"city": "南通"}})
    sched.add_cron_job(bus_crawl, hour=18, minute=10, args=['tongcheng'], kwargs={"crawl_kwargs":{"city": "苏州,张家港"}})
    sched.add_cron_job(bus_crawl, hour=19, minute=10, args=['tongcheng'], kwargs={"crawl_kwargs":{"city": "无锡"}})
    sched.add_cron_job(bus_crawl, hour=19, minute=10, args=['tongcheng'], kwargs={"crawl_kwargs":{"city": "常州"}})
    sched.add_cron_job(bus_crawl, hour=20, minute=30, args=['tongcheng'], kwargs={"crawl_kwargs":{"city": "昆山,太仓"}})
    sched.add_cron_job(bus_crawl, hour=20, minute=0, args=['tongcheng'], kwargs={"crawl_kwargs":{"city": "常熟,吴江"}})
    sched.add_cron_job(bus_crawl, hour=21, minute=0, args=['tongcheng'], kwargs={"crawl_kwargs":{"city": "镇江,宜兴"}})
    sched.add_cron_job(bus_crawl, hour=22, minute=0, args=['tongcheng'], kwargs={"crawl_kwargs":{"city": "兴化,江阴"}})
    sched.add_cron_job(bus_crawl, hour=23, minute=0, args=['tongcheng'], kwargs={"crawl_kwargs":{"city": "徐州"}})
    sched.add_cron_job(bus_crawl, hour=0, minute=0, args=['tongcheng'], kwargs={"crawl_kwargs":{"city": "连云港,扬州"}})
    sched.add_cron_job(bus_crawl, hour=1, minute=0, args=['tongcheng'], kwargs={"crawl_kwargs":{"city": "盐城"}})

    # 快巴
    sched.add_cron_job(bus_crawl, hour=20, minute=30, args=['kuaiba'], kwargs={"crawl_kwargs":{"province": "北京"}})

    # 辽宁省网
    sched.add_cron_job(bus_crawl, hour=15, minute=10, args=['lnky'], kwargs={"crawl_kwargs":{"city": "沈阳市"}})
    sched.add_cron_job(bus_crawl, hour=15, minute=20, args=['lnky'], kwargs={"crawl_kwargs":{"city": "大连市"}})
    sched.add_cron_job(bus_crawl, hour=15, minute=30, args=['lnky'], kwargs={"crawl_kwargs":{"city": "锦州市"}})
    sched.add_cron_job(bus_crawl, hour=15, minute=40, args=['lnky'], kwargs={"crawl_kwargs":{"city": "辽阳市"}})
    sched.add_cron_job(bus_crawl, hour=17, minute=10, args=['lnky'], kwargs={"crawl_kwargs":{"city": "营口市"}})
    sched.add_cron_job(bus_crawl, hour=17, minute=40, args=['lnky'], kwargs={"crawl_kwargs":{"city": "铁岭市"}})
    sched.add_cron_job(bus_crawl, hour=20, minute=10, args=['lnky'], kwargs={"crawl_kwargs":{"city": "鞍山市"}})
    sched.add_cron_job(bus_crawl, hour=20, minute=40, args=['lnky'], kwargs={"crawl_kwargs":{"city": "抚顺市"}})
    sched.add_cron_job(bus_crawl, hour=21, minute=10, args=['lnky'], kwargs={"crawl_kwargs":{"city": "本溪市"}})
    sched.add_cron_job(bus_crawl, hour=21, minute=40, args=['lnky'], kwargs={"crawl_kwargs":{"city": "丹东市"}})
    sched.add_cron_job(bus_crawl, hour=22, minute=10, args=['lnky'], kwargs={"crawl_kwargs":{"city": "阜新市"}})
    sched.add_cron_job(bus_crawl, hour=22, minute=40, args=['lnky'], kwargs={"crawl_kwargs":{"city": "葫芦岛市"}})
    sched.add_cron_job(bus_crawl, hour=23, minute=10, args=['lnky'], kwargs={"crawl_kwargs":{"city": "朝阳市"}})
    sched.add_cron_job(bus_crawl, hour=23, minute=10, args=['lnky'], kwargs={"crawl_kwargs":{"city": "盘锦市"}})

    #张家港市民网页 & 无线苏州
    sched.add_cron_job(bus_crawl, hour=23, minute=30, args=['zjgsm'], kwargs={"crawl_kwargs":{"city": "张家港"}})
    sched.add_cron_job(bus_crawl, hour=0, minute=30, args=['zjgsm'], kwargs={"crawl_kwargs":{"city": "苏州"}})
    sched.add_cron_job(bus_crawl, hour=1, minute=30, args=['zjgsm'], kwargs={"crawl_kwargs":{"city": "常熟"}})
    sched.add_cron_job(bus_crawl, hour=2, minute=0, args=['zjgsm'], kwargs={"crawl_kwargs":{"city": "太仓"}})
    sched.add_cron_job(bus_crawl, hour=2, minute=30, args=['zjgsm'], kwargs={"crawl_kwargs":{"city": "吴江"}})
    sched.add_cron_job(bus_crawl, hour=3, minute=0, args=['zjgsm'], kwargs={"crawl_kwargs":{"city": "昆山"}})

    sched.add_cron_job(bus_crawl, hour=18, minute=30, args=['wxsz'], kwargs={"crawl_kwargs":{"city": "张家港"}})
    sched.add_cron_job(bus_crawl, hour=18, minute=30, args=['wxsz'], kwargs={"crawl_kwargs":{"city": "苏州"}})
    sched.add_cron_job(bus_crawl, hour=19, minute=30, args=['wxsz'], kwargs={"crawl_kwargs":{"city": "常熟"}})
    sched.add_cron_job(bus_crawl, hour=19, minute=0, args=['wxsz'], kwargs={"crawl_kwargs":{"city": "太仓"}})
    sched.add_cron_job(bus_crawl, hour=20, minute=30, args=['wxsz'], kwargs={"crawl_kwargs":{"city": "吴江"}})
    sched.add_cron_job(bus_crawl, hour=20, minute=0, args=['wxsz'], kwargs={"crawl_kwargs":{"city": "昆山"}})


    #携程
    sched.add_cron_job(bus_crawl, hour=1, minute=0, args=['ctrip'], kwargs={"crawl_kwargs":{"province": "北京"}})

    #北京省网
    sched.add_cron_job(bus_crawl, hour=13, minute=30, args=['bjky'])

    #唐山省网
    sched.add_cron_job(bus_crawl, hour=3, minute=10, args=['hebky'], kwargs={"crawl_kwargs":{"city": "唐山"}})

    # 代理ip相关
    sched.add_interval_job(crawl_proxy_haodaili, minutes=6)
    sched.add_interval_job(crawl_proxy_samair, minutes=15)
    sched.add_interval_job(crawl_proxy_66ip, minutes=12)
    sched.add_interval_job(crawl_proxy_xici, minutes=12)
    sched.add_interval_job(crawl_proxy_zdaye, minutes=6)
    sched.add_interval_job(check_proxy, minutes=1)
    sched.add_interval_job(check_proxy_cqky, minutes=1)
    sched.add_interval_job(check_proxy_tc, minutes=1)
    sched.add_interval_job(check_proxy_cbd, minutes=1)
    sched.add_interval_job(check_proxy_scqcp, minutes=1)
    sched.add_interval_job(check_proxy_bjky, minutes=1)
    sched.add_interval_job(check_proxy_lnky, minutes=1)
    sched.add_interval_job(check_proxy_e8s, minutes=1)
    sched.add_interval_job(check_proxy_changtu, minutes=1)

    # 其他
    sched.add_cron_job(delete_source_riders, hour=22, minute=40)
    sched.add_cron_job(clear_lines, hour=1, minute=0)
    sched.add_cron_job(clear_redis_data, hour=5, minute=0)

    sched.start()

if __name__ == '__main__':
    main()
