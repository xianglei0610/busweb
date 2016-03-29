#!/usr/bin/env python
# encoding: utf-8
"""
代理ip管理

1.会有定时任务从互联网上抓代理ip下来,并保存在redis上的RK_ALL_RPOXY_IP上
2.会有定时任务检测RK_PROXY_IP_ALL上IP的可用性和速度, 不满足要求的会remove掉
3.个性化定制要求
"""

import requests
import json
import random
import urllib
import urllib2
import re

from app.constants import *
from datetime import datetime as dte, timedelta
from bs4 import BeautifulSoup
from app.utils import get_redis


class ProxyProducer(object):

    def __init__(self):
        self.consumer_list= []

    def registe_consumer(self, consumer):
        if consumer in self.consumer_list:
            return
        self.consumer_list.append(consumer)

    def crawl_from_haodaili(self):
        add_cnt = 0
        for i in range(1, 10):
            url = "http://www.haodailiip.com/guonei/%s" % i
            try:
                r = requests.get(url, timeout=10)
            except:
                continue
            soup = BeautifulSoup(r.content, "lxml")
            for s in soup.select(".proxy_table tr")[1:]:
                td_lst = s.findAll("td")
                ip, port = td_lst[0].text.strip(), td_lst[1].text.strip()
                ipstr = "%s:%s" % (ip, port)
                if self.valid_proxy(ipstr):
                    self.add_proxy(ipstr)
                    add_cnt += 1
        return add_cnt

    def crawl_from_samair(self):
        add_cnt = 0
        for i in range(1, 10):
            url = "http://www.samair.ru/proxy-by-country/China-%02d.htm" % i
            try:
                r = requests.get(url, timeout=10)
            except Exception:
                continue
            lst = re.findall(r"(\d+.\d+.\d+.\d+:\d+)", r.content)
            for ipstr in lst:
                if self.valid_proxy(ipstr):
                    self.add_proxy(ipstr)
                    add_cnt += 1
        return add_cnt

    def crawl_from_66ip(self):
        proxy_lst = set()
        for i in [2,3,4]:
            url = "http://www.66ip.cn/nmtq.php?getnum=150&isp=0&anonymoustype=%s&start=&ports=&export=&ipaddress=&area=0&proxytype=2&api=66ip" % i
            try:
                r = requests.get(url, timeout=6)
            except Exception:
                continue
            proxy_lst=proxy_lst.union(set(re.findall(r"(\d+.\d+.\d+.\d+:\d+)", r.content)))
        add_cnt = 0
        for ipstr in proxy_lst:
            if self.valid_proxy(ipstr):
                self.add_proxy(ipstr)
                add_cnt += 1
        return add_cnt



    def add_proxy(self, ipstr):
        """
        Args:
            - ipstr  eg: 127.0.0.1:88
        """
        rds = get_redis("default")
        add_cnt = rds.sadd(RK_PROXY_IP_ALL, ipstr)
        if add_cnt:     # 新增的
            for c in self.consumer_list:
                c.on_producer_add(ipstr)
        return add_cnt

    def get_proxy(self):
        rds = get_redis("default")
        ipstr = rds.srandmember(RK_PROXY_IP_ALL)
        return ipstr

    def all_proxy(self):
        rds = get_redis("default")
        return rds.smembers(RK_PROXY_IP_ALL)

    def remove_proxy(self, ipstr):
        rds = get_redis("default")
        del_cnt = rds.srem(RK_PROXY_IP_ALL, ipstr)
        if del_cnt:
            for c in self.consumer_list:
                c.on_producer_remove(ipstr)
        return del_cnt

    def proxy_size(self):
        rds = get_redis("default")
        return rds.scard(RK_PROXY_IP_ALL)

    def valid_proxy(self, ipwithport):
        """
        PS: 能访问百度不一定可以访问其他网站,在具体使用时最好再验证一遍
        """
        try:
            r = requests.get("http://www.baidu.com",
                             proxies = {"http": "http://%s" % ipwithport},
                             timeout=0.5)
        except:
            return False
        if r.status_code != 200:
            return False
        if "百度一下" not in r.content:
            return False
        return True


class ProxyConsumer(object):
    def valid_proxy(self, ipstr):
        return True

    def on_producer_add(self, ipstr):
        if self.valid_proxy(ipstr):
            self.add_proxy(ipstr)

    def on_producer_remove(self, ipstr):
        self.remove_proxy(ipstr)

    def add_proxy(self, ipstr):
        rds = get_redis("default")
        add_cnt = rds.sadd(self.PROXY_KEY, ipstr)
        return add_cnt

    def remove_proxy(self, ipstr):
        rds = get_redis("default")
        del_cnt = rds.srem(self.PROXY_KEY, ipstr)
        return del_cnt

    def all_proxy(self):
        rds = get_redis("default")
        return rds.smembers(self.PROXY_KEY)

    def proxy_size(self):
        rds = get_redis("default")
        return rds.scard(self.PROXY_KEY)


class CqkyProxyConsumer(ProxyConsumer):
    PROXY_KEY = RK_PROXY_IP_CQKY

    @property
    def current_proxy(self):
        rds = get_redis("default")
        ipstr = rds.get(RK_PROXY_CUR_CQKY)
        if ipstr and rds.sismember(RK_PROXY_IP_CQKY, ipstr):
            return ipstr
        ipstr = rds.srandmember(RK_PROXY_IP_CQKY)
        rds.set(RK_PROXY_CUR_CQKY, ipstr)
        return ipstr

    def clear_current_proxy(self):
        rds = get_redis("default")
        return rds.set(RK_PROXY_CUR_CQKY, "")

    def valid_proxy(self, ipstr):
        line_url = "http://www.96096kp.com/UserData/MQCenterSale.aspx"
        tomorrow = dte.now() + timedelta(days=1)
        params = {
            "StartStation": "重庆主城",
            "WaitStationCode": "",
            "OpStation": -1,
            "OpAddress": -1,
            "DstNode": "成都",
            "SchDate": tomorrow.strftime("%Y-%m-%d"),
            "SeatType": "",
            "SchTime": "",
            "OperMode": "",
            "SchCode": "",
            "txtImgCode": "",
            "cmd": "MQCenterGetClass",
            "isCheck": "false",
        }
        headers = {
            "User-Agent": random.choice(BROWSER_USER_AGENT),
            "Referer": "http://www.96096kp.com",
            "Origin": "http://www.96096kp.com",
            "Content-Type": "application/x-www-form-urlencoded; charset=UTF-8",
        }
        try:
            r = requests.post(line_url,
                              data=urllib.urlencode(params),
                              headers=headers,
                              timeout=2,
                              proxies={"http": "http://%s" % ipstr})
            content = r.content
            for k in set(re.findall("([A-Za-z]+):", content)):
                content = re.sub(r"\b%s\b" % k, '"%s"' % k, content)
            res = json.loads(content)
        except:
            return False
        try:
            if res["success"] != "true" or not res["data"]:
                return False
        except:
            return False
        return True



class ScqcpProxyConsumer(ProxyConsumer):
    PROXY_KEY = RK_PROXY_IP_SCQCP

    @property
    def current_proxy(self):
        rds = get_redis("default")
        ipstr = rds.get(RK_PROXY_CUR_SCQCP)
        if ipstr and rds.sismember(RK_PROXY_IP_SCQCP, ipstr):
            return ipstr
        ipstr = rds.srandmember(RK_PROXY_IP_SCQCP)
        rds.set(RK_PROXY_CUR_SCQCP, ipstr)
        return ipstr

    def clear_current_proxy(self):
        rds = get_redis("default")
        return rds.set(RK_PROXY_CUR_SCQCP, "")

    def valid_proxy(self, ipstr):
        ua = random.choice(MOBILE_USER_AGENG)
        device = "android" if "android" in ua else "ios"

        # 获取token
        uri = "/api/v1/api_token/get_token_for_app?channel=dxcd&version_code=40&oper_system=%s" % device
        url = urllib2.urlparse.urljoin(SCQCP_DOMAIN, uri)
        headers = {
            "User-Agent": ua,
            "Authorization": '',
            "Content-Type": "application/json; charset=UTF-8",
        }
        try:
            r = requests.get(url, headers=headers, timeout=2, proxies={"http": "http://%s" % ipstr})
            ret = r.json()
            if ret["token"]:
                return True
        except:
            return False
        return True


class TongChengProxyConsumer(ProxyConsumer):
    PROXY_KEY = RK_PROXY_IP_TC

    def valid_proxy(self, ipstr):
        url = "http://www.ly.com/"
        try:
            ua = random.choice(BROWSER_USER_AGENT)
            r = requests.get(url,
                             headers={"User-Agent": ua},
                             timeout=2,
                             proxies={"http": "http://%s" % ipstr})
        except:
            return False
        if r.status_code != 200 or "同程旅游" not in r.content:
            return False
        return True


class CBDProxyConsumer(ProxyConsumer):
    PROXY_KEY = RK_PROXY_IP_CBD

    def valid_proxy(self, ipstr):
        url = "http://m.chebada.com/"
        headers = {
            "User-Agent": random.choice(MOBILE_USER_AGENG),
        }
        try:
            r = requests.get(url,
                             headers=headers,
                             timeout=2,
                             proxies={"http": "http://%s" % ipstr})
        except:
            return False
        if r.status_code != 200 or "巴士管家" not in r.content:
            return False
        return True

proxy_producer = ProxyProducer()

cqky_proxy = CqkyProxyConsumer()
tc_proxy = TongChengProxyConsumer()
cbd_proxy = CBDProxyConsumer()
scqcp_proxy = ScqcpProxyConsumer()

proxy_producer.registe_consumer(cqky_proxy)
proxy_producer.registe_consumer(tc_proxy)
proxy_producer.registe_consumer(cbd_proxy)
proxy_producer.registe_consumer(scqcp_proxy)
