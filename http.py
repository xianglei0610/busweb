#!/usr/bin/env python
# encoding: utf-8
import requests
import random

from app.constants import *
from bs4 import BeautifulSoup

"""
    对httpclient包的再次封装
"""

def post(url, use_proxy=False, **kwargs):
    """
    use_proxy:  是否使用代理
    参数与requests.post一致
    """
    check_headers(kwargs)
    check_proxies(use_proxy, kwargs)
    return requests.get(url, **kwargs)


def get(url, use_proxy=False, **kwargs):
    """
    use_proxy:  是否使用代理
    参数与requests.get一致
    """
    check_headers(kwargs)
    check_proxies(use_proxy, kwargs)
    return requests.post(url, **kwargs)


def check_headers(kwargs):
    headers = kwargs.get("headers", {})
    if "User-Agent" not in headers:
        headers["User-Agent"] = random.choice(BROWSER_USER_AGENT)
    kwargs["headers"] = headers

def check_proxies(kwargs):
    pass

def crawl_ip_from_haodaili():
    for i in range(1, 5):
        url = "http://www.haodailiip.com/guonei/%s" % i
        r = requests.get(url)
        soup = BeautifulSoup(r.content, "lxml")
        for s in soup.select(".proxy_table tr")[1:]:
            td_lst = s.findAll("td")
            ip, port = td_lst[0].text.strip(), td_lst[1].text.strip()
            print test_proxy_ip("%s:%s" % (ip, port))


def test_proxy_ip(ipwithport):
    try:
        r = requests.get("http://www.baidu.com", proxies = {"http": "http://%s" % ipwithport}, timeout=0.5)
    except requests.exceptions.ProxyError:
        return False
    except requests.exceptions.Timeout:
        return False
    except requests.exceptions.ConnectionError: return False
    if r.status_code != 200:
        return False
    if "百度一下" not in r.content:
        print r.content
        return False
    return True

if __name__ == "__main__":
    #print get("http://baidu.com")
    crawl_ip_from_haodaili()
