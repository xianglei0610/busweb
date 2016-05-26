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
import re

from app.constants import *
from datetime import datetime as dte, timedelta
from bs4 import BeautifulSoup
from lxml import etree
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
        for i in range(1, 15):
            url = "http://www.haoip.cc/guonei/%s" % i
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
            from selenium import webdriver
            driver = webdriver.PhantomJS()
            driver.get(url)
            for trobj in driver.find_elements_by_tag_name("tr"):
                lst = re.findall(r"(\d+.\d+.\d+.\d+:\d+)", trobj.text)
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

    def crawl_from_zdaye(self):
        url = "http://api.zdaye.com/?api=201604061044324430&pw=efrfdaf&sleep=5%C3%EB%C4%DA&gb=2&post=%D6%A7%B3%D6&ct=200"
        proxy_lst = set()
        r = requests.get(url, timeout=6)
        proxy_lst=proxy_lst.union(set(re.findall(r"(\d+.\d+.\d+.\d+:\d+)", r.content)))
        add_cnt = 0
        for ipstr in proxy_lst:
            if self.valid_proxy(ipstr):
                self.add_proxy(ipstr)
                add_cnt += 1
        return add_cnt

    def crawl_from_xici(self):
        add_cnt = 0
        for t in ["http://www.xicidaili.com/nn/%d", "http://www.xicidaili.com/nt/%d"]:
            for i in range(1, 10):
                url = t % i
                try:
                    r = requests.get(url, timeout=10, headers={"User-Agent": "Chrome"})
                except Exception:
                    continue
                sel = etree.HTML(r.content)
                for s in sel.xpath("//tr"):
                    try:
                        lst = s.xpath("td/text()")
                        ip, port = lst[0], lst[1]
                    except:
                        continue
                    ipstr = "%s:%s" % (ip, port)
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
        from tasks import check_add_proxy_ip
        if add_cnt:     # 新增的
            for c in self.consumer_list:
                # c.on_producer_add(ipstr)
                check_add_proxy_ip.delay(c.name, ipstr)
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
                             timeout=1)
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
    name = "cqky"

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
                              timeout=4,
                              allow_redirects=False,
                              proxies={"http": "http://%s" % ipstr})
            content = r.content
            for k in set(re.findall("([A-Za-z]+):", content)):
                content = re.sub(r"\b%s\b" % k, '"%s"' % k, content)
            res = json.loads(content)
        except Exception, e:
            return False
        try:
            if res["success"] != "true" or not res["data"]:
                return False
        except:
            return False
        return True


class ScqcpProxyConsumer(ProxyConsumer):
    PROXY_KEY = RK_PROXY_IP_SCQCP
    name = "scqcp"

    def valid_proxy(self, ipstr):
        url = "http://scqcp.com/login/index.html"
        try:
            ua = random.choice(BROWSER_USER_AGENT)
            r = requests.get(url,
                             headers={"User-Agent": ua},
                             timeout=4,
                             proxies={"http": "http://%s" % ipstr})
            sel = etree.HTML(r.content)
            token = sel.xpath("//input[@id='csrfmiddlewaretoken1']/@value")[0]
            if token:
                return True
        except:
            return False
        return True


class TongChengProxyConsumer(ProxyConsumer):
    PROXY_KEY = RK_PROXY_IP_TC
    name = "tongcheng"

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
    name = "cbd"

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


class BjkyProxyConsumer(ProxyConsumer):
    PROXY_KEY = RK_PROXY_IP_BJKY
    name = "bjky"

    def valid_proxy(self, ipstr):
        url = "http://e2go.com.cn"
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
        if r.status_code != 200 or "欢迎访问北京客运信息网" not in r.content:
            return False
        return True


class LnkyProxyConsumer(ProxyConsumer):
    PROXY_KEY = RK_PROXY_IP_LNKY
    name = "lnky"

    def valid_proxy(self, ipstr):
        url = "http://www.jt306.cn/wap/login/home.do"
        headers = {
            "User-Agent": random.choice(MOBILE_USER_AGENG),
        }
        try:
            r = requests.get(url,
                             headers=headers,
                             timeout=3,
                             proxies={"http": "http://%s" % ipstr})
        except:
            return False
        if r.status_code != 200 or "辽宁省汽车客运网上售票系统" not in r.content:
            return False
        return True


class E8sProxyConsumer(ProxyConsumer):
    PROXY_KEY = RK_PROXY_IP_E8S
    name = "e8s"

    def valid_proxy(self, ipstr):
        url = "http://m.e8s.com.cn/bwfpublicservice/notice.action"
        headers = {
            "User-Agent": random.choice(MOBILE_USER_AGENG),
        }
        data = {
                "page": "1",
                "rowNum": "10"
                }
        try:
            r = requests.post(url,
                              data=data,
                              headers=headers,
                              timeout=3,
                              proxies={"http": "http://%s" % ipstr})
        except:
            return False
        if r.status_code != 200:
            return False
        return True


class ChangtuProxyConsumer(ProxyConsumer):
    PROXY_KEY = "proxy:changtu"
    name = "changtu"

    def valid_proxy(self, ipstr):
        url = "http://www.changtu.com"
        headers = {"User-Agent": random.choice(BROWSER_USER_AGENT)}
        try:
            r = requests.get(url,
                             headers=headers,
                             timeout=3,
                             proxies={"http": "http://%s" % ipstr})
        except:
            return False
        if r.status_code != 200 or "畅途网" not in r.content:
            return False
        return True


class Bus365ProxyConsumer(ProxyConsumer):
    PROXY_KEY = "proxy:bus365"
    name = "bus365"

    def valid_proxy(self, ipstr):
        headers = {
            "Charset": "UTF-8",
            "Content-Type": "application/x-www-form-urlencoded;",
            "User-Agent": 'Apache-HttpClient/UNAVAILABLE (java 1.4)',
            'Accept-Language': 'zh-CN,zh;q=0.8,en-US;q=0.5,en;q=0.3',
            "Connection": "keep-alive",
            "accept": "application/json,",
        }
        init_params = {
            "token": '{"clienttoken":"","clienttype":"android"}',
            "clienttype": "android",
            "usertoken": ''
            }
        params = {
           "pagenum": "1",
           "pagesize": "10"
        }
        params.update(init_params)
        url = "http://www.bus365.com/app/noticepage/0"
        notice_url = "%s?%s" % (url, urllib.urlencode(params))
        try:
            r = requests.get(notice_url,
                             headers=headers,
                             timeout=3,
                             proxies={"http": "http://%s" % ipstr})
            res = r.json()
        except:
            return False
        if r.status_code != 200 or res['totalpage'] == 0:
            return False
        return True

proxy_producer = ProxyProducer()

if "proxy_list" not in globals():
    proxy_list = {}

    proxy_list[CqkyProxyConsumer.name] = CqkyProxyConsumer()
    proxy_list[TongChengProxyConsumer.name] = TongChengProxyConsumer()
    proxy_list[CBDProxyConsumer.name] = CBDProxyConsumer()
    proxy_list[ScqcpProxyConsumer.name] = ScqcpProxyConsumer()
    proxy_list[BjkyProxyConsumer.name] = BjkyProxyConsumer()
    proxy_list[LnkyProxyConsumer.name] = LnkyProxyConsumer()
    proxy_list[E8sProxyConsumer.name] = E8sProxyConsumer()
    proxy_list[ChangtuProxyConsumer.name] = ChangtuProxyConsumer()
    proxy_list[Bus365ProxyConsumer.name] = Bus365ProxyConsumer()

    for name, obj in proxy_list.items():
        proxy_producer.registe_consumer(obj)


def get_proxy(name):
    return proxy_list[name]
