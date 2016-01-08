# -*- coding:utf-8 -*-
import random
import requests
import urllib
import urllib2
import re
import time
import cPickle

from app.constants import *
from datetime import datetime as dte
from flask import json
from lxml import etree
from contextlib import contextmanager
from app import db
from app.utils import md5, getRedisObj
from app import rebot_log, order_status_log


class AdminUser(db.Document):
    """
    后台管理员/客服
    """
    username = db.StringField(max_length=30)
    password = db.StringField(max_length=50)
    create_datetime = db.DateTimeField(default=dte.now)
    is_switch = db.IntField()
    is_kefu = db.IntField()
    is_admin = db.IntField(default=0)

    meta = {
        "indexes": [
            "username",
            "is_kefu",
            "is_switch",
        ],
    }

    @property
    def is_authenticated(self):
        return True

    @property
    def is_active(self):
        return True

    @property
    def is_anonymous(self):
        return False

    def get_id(self):
        return self.username


class PushUserList(db.Document):
    """
    push用户列表
    """
    username = db.StringField(unique=True)
    push_id = db.StringField(max_length=50)
    client = db.StringField(max_length=50)
    create_datetime = db.DateTimeField(default=dte.now)
    update_datetime = db.DateTimeField()

    meta = {
        "indexes": [
            "username",
        ],
    }


class OpenCity(db.Document):
    """
    开放城市
    """
    province = db.StringField()
    city_name = db.StringField(unique=True)
    city_code = db.StringField()
    pre_sell_days = db.IntField()
    open_time = db.StringField()
    end_time = db.StringField()
    advance_order_time = db.IntField()
    crawl_source = db.StringField()
    max_ticket_per_order = db.IntField()
    is_active = db.BooleanField(default=True)

    meta = {
        "indexes": [
            "city_name",
            "crawl_source",
            "is_active",
        ],
    }


class Starting(db.Document):
    """
    出发地
    """

    starting_id = db.StringField(unique=True)
    province_name = db.StringField()
    city_id = db.StringField()
    city_name = db.StringField()
    station_id = db.StringField()
    station_name = db.StringField()
    city_pinyin = db.StringField()
    city_pinyin_prefix = db.StringField()
    station_pinyin = db.StringField()
    station_pinyin_prefix = db.StringField()
    is_pre_sell = db.BooleanField(default=True)   # 是否预售
    crawl_source = db.StringField()

    meta = {
        "indexes": [
            "starting_id",
            "city_name",
            "station_name",
            "city_pinyin_prefix",
            "station_pinyin_prefix",
            "crawl_source",
            ],
    }

    @property
    def pre_sell_days(self):
        """
        预售期
        """
        if not self.is_pre_sell:
            return 0
        if self.province_name == "四川" and self.crawl_source == "scqcp":
            return 10
        elif self.province_name == "广西" and self.crawl_source == "bus100":
            return 15
        return 0

    @property
    def open_time(self):
        return "08:00:00"

    @property
    def end_time(self):
        return "23:00:00"

    @property
    def advance_order_time(self):
        "单位：分钟"
        if self.crawl_source in ["scqcp", "ctrip"]:
            return 120  # 2hour
        return 0

    @property
    def max_ticket_per_order(self):
        if self.crawl_source in ["scqcp", "ctrip"]:
            return 5
        return 3


class Destination(db.Document):
    """
    目的地
    """

    destination_id = db.StringField(unique=True)
    starting = db.ReferenceField(Starting)
    city_id = db.StringField()
    city_name = db.StringField()
    city_pinyin = db.StringField()
    city_pinyin_prefix = db.StringField()
    station_id = db.StringField()
    station_name = db.StringField()
    station_pinyin = db.StringField()
    station_pinyin_prefix = db.StringField()
    crawl_source = db.StringField()

    meta = {
        "indexes": [
            "destination_id",
            "city_name",
            "station_name",
            "city_pinyin_prefix",
            "station_pinyin_prefix",
            "crawl_source",
            ],
    }


class Line(db.Document):
    """
    线路表
    """
    line_id = db.StringField(unique=True)  # 路线id, 必须唯一
    crawl_source = db.StringField(required=True)     # 爬取来源
    starting = db.ReferenceField(Starting)
    destination = db.ReferenceField(Destination)
    drv_date = db.StringField(required=True)  # 开车日期 yyyy-MM-dd
    drv_time = db.StringField(required=True)  # 开车时间 hh:mm
    drv_datetime = db.DateTimeField()         # DateTime类型的开车时间
    distance = db.StringField()
    vehicle_type = db.StringField()  # 车型
    seat_type = db.StringField()     # 座位类型
    bus_num = db.StringField()       # 车次/班次
    full_price = db.FloatField()
    half_price = db.FloatField()
    fee = db.FloatField()                 # 手续费
    crawl_datetime = db.DateTimeField()   # 爬取的时间
    extra_info = db.DictField()           # 额外信息字段
    left_tickets = db.IntField()          # 剩余票数
    update_datetime = db.DateTimeField()  # 更新时间
    refresh_datetime = db.DateTimeField()   # 线路刷新时间

    meta = {
        "indexes": [
            "line_id",
            "crawl_source",
            "drv_date",
            "drv_time",
            "drv_datetime",
            "crawl_datetime",
            ],
    }

    def real_price(self):
        return self.fee+self.full_price

    def get_json(self):
        """
        传给客户端的格式和数据，不能轻易修改！
        """
        return {
            "line_id": self.line_id,
            "starting_city": self.starting.city_name,
            "starting_station": self.starting.station_name,
            "destination_city": self.destination.city_name,
            "destination_station": self.destination.station_name,
            "bus_num": self.bus_num,
            "drv_date": self.drv_date,
            "drv_time": self.drv_time,
            "vehicle_type": self.vehicle_type,
            "full_price": self.full_price,
            "half_price": self.half_price,
            "left_tickets": self.left_tickets,
            "fee": self.fee,
            "distance": self.distance,
        }


class Order(db.Document):
    """
    一个订单只对应一条线路
    """
    # 订单信息
    order_no = db.StringField(unique=True)
    out_order_no = db.StringField()
    raw_order_no = db.StringField()
    status = db.IntField()
    order_price = db.FloatField()  # 订单金额, 12308平台传来的金额
    create_date_time = db.DateTimeField()

    # 车票信息
    line = db.ReferenceField(Line)

    seat_no_list = db.ListField(db.StringField(max_length=10))
    ticket_price = db.FloatField()          # 单张车票价格
    ticket_amount = db.IntField()
    ticket_fee = db.FloatField()            # 单张车票手续费
    discount = db.FloatField(default=0)     # 单张车票优惠金额

    # 支付信息
    pay_money = db.FloatField()     # 实际要支付的金额
    pay_url = db.StringField()      # 支付链接

    # 乘客和联系人信息
    # 包含字段: name, telephone, id_type,id_number,age_level
    contact_info = db.DictField()
    riders = db.ListField(db.DictField())

    # 锁票信息: 源网站在锁票这步返回的数据
    lock_datetime = db.DateTimeField()
    lock_info = db.DictField()

    # 取票信息
    pick_code_list = db.ListField(db.StringField(max_length=30))     # 取票密码
    pick_msg_list = db.ListField(db.StringField(max_length=300))      # 取票说明, len(pick_code_list)必须等于len(pick_msg_list)

    # 其他
    crawl_source = db.StringField()     # 源网站
    extra_info = db.DictField()         # 额外信息
    locked_return_url = db.URLField()   # 锁票成功回调
    issued_return_url = db.URLField()   # 出票成功回调

    # 下单时使用的源网站账号
    source_account = db.StringField()

    kefu_username = db.StringField()
    kefu_order_status = db.IntField()   # 1表示已处理
    kefu_updatetime = db.DateTimeField()

    drv_datetime = db.DateTimeField()         # DateTime类型的开车时间
    bus_num = db.StringField()       # 车次/班次
    starting_name = db.StringField()
    destination_name = db.StringField()


    meta = {
        "indexes": [
            "order_no",
            "out_order_no",
            "raw_order_no",
            "status",
            "crawl_source",
            "-create_date_time",
        ],
    }

    @property
    def source_account_pass(self):
        accounts = SOURCE_INFO.get(self.crawl_source, {}).get("accounts", {})
        pass_info = accounts.get(self.source_account, [])
        if not pass_info:
            return ""
        return pass_info[0]

    def get_rebot(self, type="app"):  # type: app or wap or web
        if self.crawl_source == "scqcp":
            if type == "app":
                rebot = ScqcpRebot.objects.get(telephone=self.source_account)
                return rebot
        elif self.crawl_source == "ctrip":
            rebot = CTripRebot.objects.get(telephone=self.source_account)
            return rebot
        elif self.crawl_source == "cbd":
            rebot = CBDRebot.objects.get(telephone=self.source_account)
            return rebot
        return None

    def complete_by(self, user_obj):
        self.kefu_order_status = 1
        self.kefu_updatetime = dte.now()
        self.kefu_username = user_obj.username
        self.modify(
                kefu_order_status=1,
                kefu_updatetime=dte.now(),
                kefu_username=user_obj.username)
        r = getRedisObj()
        key = 'order_list:%s' % user_obj.username
        r.srem(key, self.order_no)

    def on_create(self):
        if self.status != STATUS_WAITING_LOCK:
            return
        order_status_log.info("[on_create] out_order_no: %s", self.out_order_no)

    def on_lock_fail(self, reason=""):
        if self.status != STATUS_LOCK_FAIL:
            return
        order_status_log.info("[on_lock_fail] order: %s, out_order_no: %s, reason:%s", self.order_no, self.out_order_no, reason)

        r = getRedisObj()
        r.zrem('lock_order_list', self.order_no)

        rebot = self.get_rebot()
        if rebot:
            rebot.remove_doing_order(self)

    def on_lock_success(self):
        if self.status != STATUS_WAITING_ISSUE:
            return
        order_status_log.info("[on_lock_success] order:%s, out_order_no: %s", self.order_no, self.out_order_no)

        r = getRedisObj()
        r.zadd('lock_order_list', self.order_no, time.time())

    def on_lock_retry(self):
        if self.status != STATUS_LOCK_RETRY:
            return
        order_status_log.info("[on_lock_retry] order:%s", self.order_no)

        r = getRedisObj()
        r.zadd('lock_order_list', self.order_no, time.time())

    def on_give_back(self, reason=""):
        if self.status != STATUS_GIVE_BACK:
            return
        order_status_log.info("[on_give_back] order:%s, out_order_no: %s, reason:%s", self.order_no, self.out_order_no, reason)

        rebot = self.get_rebot()
        if rebot:
            rebot.remove_doing_order(self)

        r = getRedisObj()
        key = RK_ISSUE_FAIL_COUNT % self.crawl_source
        r.delete(key)

    def on_issue_fail(self, reason=""):
        if self.status != STATUS_ISSUE_FAIL:
            return
        order_status_log.info("[on_issue_fail] order:%s, out_order_no: %s, reason:%s", self.order_no, self.out_order_no, reason)

        rebot = self.get_rebot()
        if rebot:
            rebot.remove_doing_order(self)

        from tasks import issue_fail_send_email
        r = getRedisObj()
        key = RK_ISSUE_FAIL_COUNT % self.crawl_source
        r.sadd(key, self.order_no)
        order_ct = r.scard(key)
        if order_ct > ISSUE_FAIL_WARNING:
            issue_fail_send_email.delay(key)

    def on_issueing(self):
        if self.status != STATUS_ISSUE_ING:
            return
        order_status_log.info("[on_issueing] order:%s, out_order_no: %s", self.order_no, self.out_order_no)

        rebot = self.get_rebot()
        if rebot:
            rebot.remove_doing_order(self)

    def on_issue_success(self):
        if self.status != STATUS_ISSUE_SUCC:
            return
        order_status_log.info("[on_issue_sucess] order:%s, out_order_no: %s", self.order_no, self.out_order_no)

        r = getRedisObj()
        key = RK_ISSUE_FAIL_COUNT % self.crawl_source

        r.delete(key)
        rebot = self.get_rebot()
        if rebot:
            rebot.remove_doing_order(self)

    def get_contact_info(self):
        """
        返回给client的数据和格式， 不要轻易修改!
        """
        info = self.contact_info
        return {
            "name": info["name"],
            "telephone": info["telephone"],
            "id_type": info.get("idtype", IDTYPE_IDCARD),
            "id_number": info.get("id_number", ""),
            "age_level": info.get('age_level', RIDER_ADULT),
        }

    def get_rider_info(self):
        """
        返回给client的数据和格式， 不要轻易修改!
        """
        lst = []
        for info in self.riders:
            lst.append({
                "name": info["name"],
                "telephone": info["telephone"],
                "id_type": info.get("idtype", IDTYPE_IDCARD),
                "id_number": info.get("id_number", ""),
                "age_level": info.get('age_level', RIDER_ADULT),
            })
        return lst

    @classmethod
    def generate_order_no(cls):
        """
        组成：
        年(4)+月(2)+日(2)+毫秒(6)+随机数(2)
        """
        now = dte.now()
        sdate = now.strftime("%Y%m%d")
        micro = "%06d" % now.microsecond
        srand = "%02d" % random.randrange(10, 100)
        return "%s%s%s" % (sdate, micro, srand)


class Rebot(db.Document):
    """
    机器人: 对被爬网站用户的抽象
    """

    telephone = db.StringField(required=True, unique=True)
    password = db.StringField()
    is_active = db.BooleanField(default=True)   # 是否有效
    is_locked = db.BooleanField(default=False)  # 是否被锁
    last_login_time = db.DateTimeField(default=dte.now)  # 最近一次登录时间
    doing_orders = db.DictField()   # 正在处理的订单

    meta = {
        "abstract": True,
    }

    @classmethod
    def get_one(cls):
        qs = cls.objects.filter(is_active=True, is_locked=False)
        if not qs:
            return
        size = qs.count()
        rd = random.randint(0, size-1)
        return qs[rd]

    @classmethod
    @contextmanager
    def get_and_lock(cls, order):
        obj = cls.get_one()
        if obj:
            obj.add_doing_order(order)
            rebot_log.info("[get_and_lock] succ. tele: %s, order: %s", obj.telephone, order.order_no)
        else:
            rebot_log.info("[get_and_lock] fail. order: %s", order.order_no)
        try:
            yield obj
        except Exception, e:
            if obj:
                obj.remove_doing_order(order)
            raise e

    def add_doing_order(self, order):
        d = self.doing_orders
        if order.order_no in d:
            return
        d[order.order_no] = 1
        self.modify(doing_orders=d)
        self.on_add_doing_order(order)

    def remove_doing_order(self, order):
        d = self.doing_orders
        if order.order_no in d:
            del d[order.order_no]
            self.modify(doing_orders=d)
            self.on_remove_doing_order(order)

    def on_add_doing_order(self, order):
        pass

    def on_remove_doing_order(self, order):
        pass

    def valid(self):
        """
        验证此账号是否有效
        """
        return True

    def login(self):
        """
        登录成功返回"OK", 失败返回其他字符串。
        """
        raise Exception("Not Implemented")


class ScqcpRebot(Rebot):
    is_encrypt = db.IntField(choices=(0, 1))
    user_agent = db.StringField()
    token = db.StringField()
    open_id = db.StringField()

    meta = {
        "indexes": ["telephone", "is_active", "is_locked"],
    }

    def on_add_doing_order(self, order):
        self.modify(is_locked=True)

    def on_remove_doing_order(self, order):
        self.modify(is_locked=False)

    def login(self):
        ua = random.choice(MOBILE_USER_AGENG)
        device = "android" if "android" in ua else "ios"

        # 获取token
        uri = "/api/v1/api_token/get_token_for_app?channel=dxcd&version_code=40&oper_system=%s" % device
        ret = self.http_post(uri, "")
        token = ret["token"]
        self.user_agent = ua
        self.token = token

        # 登陆
        uri = "/api/v1/user/login_phone"
        data = {
            "username": self.telephone,
            "password": self.password,
            "is_encrypt": self.is_encrypt,
        }
        ret = self.http_post(uri, data)
        if "open_id" not in ret:
            # 登陆失败
            self.is_active = False
            self.last_login_time = dte.now()
            self.save()
            return ret.get("msg", "fail")
        else:
            # 登陆成功
            self.is_active = True
            self.last_login_time = dte.now()
            self.open_id = ret["open_id"]
            self.save()
            return "OK"

    @classmethod
    def login_all(cls):
        # 登陆所有预设账号
        rebot_log.info(">>>> start to login scqcp.com:")
        valid_cnt = 0
        has_checked = {}
        accounts = SOURCE_INFO[SOURCE_SCQCP]["accounts"]
        for bot in cls.objects:
            has_checked[bot.telephone] = 1
            if bot.telephone not in accounts:
                bot.modify(is_active=False)
                continue
            pwd, is_encrypt = accounts[bot.telephone]
            bot.modify(password=pwd, is_encrypt=is_encrypt)

            if bot.login() == "OK":
                rebot_log.info("%s 登陆成功" % bot.telephone)
                valid_cnt += 1

        for tele, (pwd, is_encrypt) in accounts.items():
            if tele in has_checked:
                continue
            bot = cls(is_active=False,
                      is_locked=False,
                      telephone=tele,
                      password=pwd,
                      is_encrypt=is_encrypt)
            bot .save()
            if bot.login() == "OK":
                rebot_log.info("%s 登陆成功" % bot.telephone)
                valid_cnt += 1
        rebot_log.info(">>>> end login scqcp.com, success %d", valid_cnt)

    def http_post(self, uri, data, user_agent="", token=""):
        url = urllib2.urlparse.urljoin(SCQCP_DOMAIN, uri)
        request = urllib2.Request(url)
        request.add_header('User-Agent', user_agent or self.user_agent)
        request.add_header('Authorization', token or self.token)
        request.add_header('Content-type', "application/json; charset=UTF-8")
        qstr = urllib.urlencode(data)
        response = urllib2.urlopen(request, qstr, timeout=30)
        ret = json.loads(response.read())
        return ret

class CBDRebot(Rebot):
    user_agent = db.StringField()
    cookies = db.StringField()

    meta = {
        "indexes": ["telephone", "is_active", "is_locked"],
    }


    def login(self):
        ua = random.choice(MOBILE_USER_AGENG)
        log_url = "http://m.chebada.com/Account/UserLogin"
        data = {
            "MobileNo": self.telephone,
            "Password": self.password,
        }
        header = {
            "User-Agent": ua,
        }
        r = requests.post(log_url, data=data, headers=header)
        ret = r.json()
        if int(ret["response"]["header"]["rspCode"]) == 0:
            self.is_active = True
            self.last_login_time = dte.now()
            self.user_agent = ua
            self.cookies = json.dumps(dict(r.cookies))
            self.save()
            return "OK"
        else:
            rebot_log.error("登陆错误cbd %s", str(ret))
        return "fail"

    @classmethod
    def login_all(cls):
        # 登陆所有预设账号
        rebot_log.info(">>>> start to login chebada.com:")
        valid_cnt = 0
        has_checked = {}
        accounts = SOURCE_INFO[SOURCE_CBD]["accounts"]
        for bot in cls.objects:
            has_checked[bot.telephone] = 1
            if bot.telephone not in accounts:
                bot.modify(is_active=False)
                continue
            pwd, _ = accounts[bot.telephone]
            bot.modify(password=pwd)
            if bot.login() == "OK":
                rebot_log.info("%s 登陆成功" % bot.telephone)
                valid_cnt += 1

        for tele, (pwd, openid) in accounts.items():
            if tele in has_checked:
                continue
            bot = cls(is_active=False,
                      is_locked=False,
                      telephone=tele,
                      password=pwd,)
            bot.save()
            if bot.login() == "OK":
                rebot_log.info("%s 登陆成功" % bot.telephone)
                valid_cnt += 1
        rebot_log.info(">>>> end login chebada.com, success %d", valid_cnt)


class CTripRebot(Rebot):
    user_agent = db.StringField()
    head = db.DictField()

    meta = {
        "indexes": ["telephone", "is_active", "is_locked"],
    }

    #@classmethod
    #def get_one(cls):
    #    r = getRedisObj()

    #    def _check_current():
    #        current = r.hget(CURRENT_ACCOUNT, "ctrip")
    #        if current:
    #            used = r.hget(ACCOUNT_ORDER_COUNT, "ctrip%s" % current)
    #            if not used or (used and int(used) < 20):
    #                r.hset(ACCOUNT_ORDER_COUNT, "ctrip%s" % current, int(used)+1)
    #                return cls.objects.get(telephone=current)
    #        return None

    #    def _choose_new():
    #        ids = []
    #        for obj in cls.objects:
    #            used = r.hget(ACCOUNT_ORDER_COUNT, "ctrip%s" % obj.telephone)
    #            ids.append(obj.telephone)
    #            if used and int(used) >= 20:
    #                continue
    #            r.hset(CURRENT_ACCOUNT, "ctrip", obj.telephone)
    #            r.hset(ACCOUNT_ORDER_COUNT, "ctrip%s" % obj.telephone, 1)
    #            return obj, ids
    #        return None, []

    #    obj = _check_current()
    #    if obj:
    #        return obj

    #    obj, ids = _choose_new()
    #    if obj:
    #        return obj

    #    r.hdel(CURRENT_ACCOUNT, "ctrip")
    #    map(lambda k: r.hdel(ACCOUNT_ORDER_COUNT, "ctrip%s" % k), ids)
    #    new, _ = _choose_new()
    #    return new

    def login(self):
        from selenium import webdriver
        from selenium.webdriver.common.desired_capabilities import DesiredCapabilities
        from selenium.webdriver.support import expected_conditions as EC
        from selenium.webdriver.common.by import By
        from selenium.webdriver.support.ui import WebDriverWait

        dcap = dict(DesiredCapabilities.PHANTOMJS)
        dcap["phantomjs.page.settings.userAgent"] = (
            "Mozilla/5.0 (Macintosh; Intel Mac OS X 10.9; rv:25.0) Gecko/20100101 Firefox/25.0 "
        )
        #driver = webdriver.PhantomJS(desired_capabilities=dcap)
        driver = webdriver.Firefox()
        driver.set_window_size(1120, 550)
        login = "https://accounts.ctrip.com/H5Login/Index"
        driver.get(login)
        wait = WebDriverWait(driver, 10)
        username = wait.until(EC.presence_of_element_located((By.ID, "username")))
        username.send_keys(self.telephone)
        password = wait.until(EC.presence_of_element_located((By.ID, "password")))
        password.send_keys(self.password)
        submit = wait.until(EC.element_to_be_clickable((By.ID, 'submit')))
        submit.click()

        for i in range(10):
            time.sleep(1)
            text = driver.execute_script("return localStorage.HEADSTORE")
            if not text:
                continue
            ret = json.loads(text)
            head = ret["value"]
            if head["auth"]:
                ua = random.choice(MOBILE_USER_AGENG)
                self.user_agent = ua
                self.is_active = True
                self.last_login_time = dte.now()
                self.head = head
                self.save()
                driver.quit()
                print "OK", self.head, self.telephone
                return "OK"
        driver.quit()
        print 'fail', self.telephone
        rebot_log.info("%s 登陆失败" % self.telephone)
        return "fail"

    @classmethod
    def login_all(cls):
        # 登陆所有预设账号
        rebot_log.info(">>>> start to login ctrip.com:")
        valid_cnt = 0
        has_checked = {}
        accounts = SOURCE_INFO[SOURCE_CTRIP]["accounts"]
        for bot in cls.objects:
            has_checked[bot.telephone] = 1
            if bot.telephone not in accounts:
                bot.modify(is_active=False)
                continue
            pwd, _ = accounts[bot.telephone]
            bot.modify(password=pwd)
            if bot.login() == "OK":
                rebot_log.info("%s 登陆成功" % bot.telephone)
                valid_cnt += 1

        for tele, (pwd, openid) in accounts.items():
            if tele in has_checked:
                continue
            bot = cls(is_active=False,
                      is_locked=False,
                      telephone=tele,
                      password=pwd,)
            bot.save()
            if bot.login() == "OK":
                rebot_log.info("%s 登陆成功" % bot.telephone)
                valid_cnt += 1
        rebot_log.info(">>>> end login ctrip.com, success %d", valid_cnt)

    def http_post(self, url, data):
        request = urllib2.Request(url)
        request.add_header('User-Agent', self.user_agent)
        request.add_header('Content-type', "application/json; charset=UTF-8")
        qstr = json.dumps(data)
        response = urllib2.urlopen(request, qstr, timeout=30)
        ret = json.loads(response.read())
        return ret


class Bus100Rebot(Rebot):
    is_encrypt = db.IntField(choices=(0, 1))
    user_agent = db.StringField()
    token = db.StringField()
    open_id = db.StringField()
    cookies = db.DictField()

    meta = {
        "indexes": ["telephone", "is_active", "is_locked"],
    }

    @classmethod
    def get_random_rebot(cls):
        qs = cls.objects.all()
        if not qs:
            return None
        size = qs.count()
        rd = random.randint(0, size-1)
        return qs[rd]

    @classmethod
    def get_random_active_rebot(cls):
        qs = cls.objects.filter(is_active=True)
        if not qs:
            return None
        size = qs.count()
        rd = random.randint(0, size-1)
        return qs[rd]

    def on_add_doing_order(self, order):
        pass

    def on_remove_doing_order(self, order):
        pass

    def login(self):
        """
        返回OK表示登陆成功
        """
        ua = random.choice(MOBILE_USER_AGENG)

        # 登陆
        uri = "/wap/login/ajaxLogin.do"
        data = {
            "mobile": self.telephone,
            "password": self.password,
            "phone": '',
            "code": ''
        }
        ret = self.http_post(uri, data, user_agent=ua)
        if ret['returnCode'] != "0000":
            # 登陆失败
            rebot_log.error("%s %s login failed! %s", self.telephone, self.password, ret.get("returnMsg", ""))
            self.modify(is_active=False)
            return ret.get("returnMsg", "fail")

        self.modify(is_active=True, last_login_time=dte.now(), user_agent=ua)
        return "OK"

    @classmethod
    def login_all(cls):
        """登陆所有预设账号"""
        rebot_log.info(">>>> start to init 84100:")
        valid_cnt = 0
        has_checked = {}
        accounts = SOURCE_INFO[SOURCE_BUS100]["accounts"]
        for bot in cls.objects:
            has_checked[bot.telephone] = 1
            if bot.telephone not in accounts:
                bot.modify(is_active=False)
                continue
            pwd, openid = accounts[bot.telephone]
            bot.modify(password=pwd, open_id=openid)

#             if bot.login() == "OK":
#                 rebot_log.info("%s 登陆成功" % bot.telephone)
#                 valid_cnt += 1

        for tele, (pwd, openid) in accounts.items():
            if tele in has_checked:
                continue
            bot = cls(is_active=False,
                      is_locked=False,
                      telephone=tele,
                      password=pwd,
                      open_id=openid)
            bot.save()
#             if bot.login() == "OK":
#                 rebot_log.info("%s 登陆成功" % bot.telephone)
            valid_cnt += 1
        print valid_cnt
        rebot_log.info(">>>> end init 84100 success %d", valid_cnt)

    def http_post(self, uri, data, user_agent=None, token=None):
        url = urllib2.urlparse.urljoin(Bus100_DOMAIN, uri)
        request = urllib2.Request(url)
        request.add_header('User-Agent', user_agent or self.user_agent)
        qstr = urllib.urlencode(data)
        response = urllib2.urlopen(request, qstr, timeout=30)
        ret = json.loads(response.read())
        return ret

    def recrawl_shiftid(self, line):
        """
        重新获取线路ID
        """
        queryline_url = 'http://www.84100.com/getTrainList/ajax'
        start_city_id = line.starting.station_id
        start_city_name = line.starting.city_name
        target_city_name = line.destination.station_name
        sdate = line.drv_date
        drv_time = line.drv_time
        if drv_time > '00:00' and drv_time <= '12:00':
            sendTimes = "00:00-12:00"
        elif drv_time > '12:00' and drv_time <= '18:00':
            sendTimes = "12:00-18:00"
        elif drv_time > '18:00' and drv_time <= '24:00':
            sendTimes = "18:00-24:00"
        else:
            sendTimes = ''
        payload = {
            'companyNames': '',
            'endName': target_city_name,
            "isExpressway": '',
            "sendDate": sdate,
            "sendTimes": sendTimes,
            "showRemainOnly": '',
            "sort": "1",
            "startId": start_city_id,
            'startName': start_city_name,
            'stationIds': '',
            'ttsId': ''
            }
        self.recrawl_func(queryline_url, payload)

    def recrawl_func(self, queryline_url, payload):
        res = requests.post(queryline_url, data=payload)
        trainListInfo = res.json()
        if trainListInfo:
            nextPage = int(trainListInfo['nextPage'])
            pageNo = int(trainListInfo['pageNo'])
            sel = etree.HTML(trainListInfo['msg'])
            trains = sel.xpath('//div[@class="trainList"]')
            for n in trains:
                item = {}
                time = n.xpath('ul/li[@class="time"]/p/strong/text()')
                item['drv_time'] = time[0]
                departure_time = payload['sendDate']+' '+time[0]
                banci = n.xpath('ul/li[@class="time"]/p[@class="banci"]/text()')
                banci = banci[0]
                price = n.xpath('ul/li[@class="price"]/strong/text()')
                item["full_price"] = float(str(price[0]).split('￥')[-1])
                infor = n.xpath('ul/li[@class="infor"]/p/text()')
                distance = infor[1].replace('\r\n', '').replace(' ',  '')
                item['distance'] = distance
                buyInfo = n.xpath('ul/li[@class="buy"]')
                flag = 0
                shiftid = '0'
                for buy in buyInfo:
                    flag = buy.xpath('a[@class="btn"]/text()')   #判断可以买票
                    if flag:
                        flag = 1
                        shiftInfo = buy.xpath('a[@class="btn"]/@onclick')
                        if shiftInfo:
                            shift = re.findall("('(.*)')", shiftInfo[0])
                            if shift:
                                shiftid = shift[0][1]
                    else:
                        flag = '0'
                item['extra_info'] = {"flag": flag}
                item['bus_num'] = str(shiftid)
                line_id = md5("%s-%s-%s-%s-%s-%s" % \
                    (payload['startName'], payload['startId'], payload['endName'], departure_time, banci, 'bus100'))
                
                item['line_id'] = line_id
                try:
                    line_obj = Line.objects.get(line_id=line_id, crawl_source='bus100')
                    line_obj.modify(**item)
                except Line.DoesNotExist:
                    continue
            if nextPage > pageNo:
                url = queryline_url.split('?')[0]+'?pageNo=%s'%nextPage
                self.recrawl_func(url, payload)
