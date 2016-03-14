#!/usr/bin/env python
# encoding: utf-8
import requests
import random

from app.constants import *

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

if __name__ == "__main__":
    print get("http://baidu.com")
