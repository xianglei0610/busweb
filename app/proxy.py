#!/usr/bin/env python
# encoding: utf-8
"""
代理ip管理

1.会有定时任务从互联网上抓代理ip下来,并保存在redis上的RK_ALL_RPOXY_IP上
2.会有定时任务检测RK_ALL_PROXY_IP上IP的可用性和速度, 不满足要求的会remove掉
3.个性化定制要求
"""

import requests

from app.constants import *
from bs4 import BeautifulSoup
from app.utils import get_redis


def crawl_ip_from_haodaili():
    for i in range(1, 6):
        url = "http://www.haodailiip.com/guonei/%s" % i
        try:
            r = requests.get(url)
        except:
            continue
        soup = BeautifulSoup(r.content, "lxml")
        for s in soup.select(".proxy_table tr")[1:]:
            td_lst = s.findAll("td")
            ip, port = td_lst[0].text.strip(), td_lst[1].text.strip()
            ipstr = "%s:%s" % (ip, port)
            if valid_proxy_ip(ipstr):
                add_proxy_ip(ipstr)


def add_proxy_ip(ipstr):
    """
    Args:
        - ipstr  eg: 127.0.0.1:88
    """
    rds = get_redis("default")
    rds.sadd(RK_ALL_PROXY_IP, ipstr)


def get_proxy_ip():
    rds = get_redis("default")
    ipstr = rds.srandmember(RK_ALL_PROXY_IP)
    return ipstr


def remove_proxy_ip(ipstr):
    rds = get_redis("default")
    rds.srem(RK_ALL_PROXY_IP, ipstr)


def proxy_ip_size():
    rds = get_redis("default")
    return rds.scard(RK_ALL_PROXY_IP)


def valid_proxy_ip(ipwithport):
    """
    PS: 能访问百度不一定可以访问其他网站,在具体使用时最好再验证一遍
    """
    try:
        r = requests.get("http://www.baidu.com", proxies = {"http": "http://%s" % ipwithport}, timeout=0.5)
    except:
        return False
    if r.status_code != 200:
        return False
    if "百度一下" not in r.content:
        return False
    return True

def check_all_proxy_ip():
    rds = get_redis("default")
    invalid = 0
    for ipstr in rds.smembers(RK_ALL_PROXY_IP):
        if not valid_proxy_ip(ipstr):
            invalid += 1
            remove_proxy_ip(ipstr)
    return {"del": invalid, "reserve": rds.scard(RK_ALL_PROXY_IP)}
