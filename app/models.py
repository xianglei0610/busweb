# -*- coding:utf-8 -*-
import random
import requests
import urllib
import urllib2
import time
import urlparse
import assign
import re

from collections import OrderedDict
from app.constants import *
from datetime import datetime as dte
from flask import json
from lxml import etree
from bs4 import BeautifulSoup
from contextlib import contextmanager
from app import db
from app.utils import md5, getRedisObj, get_redis, trans_js_str, vcode_cqky, vcode_scqcp
from app import rebot_log, line_log


class AdminUser(db.Document):
    """
    后台管理员/客服
    """
    username = db.StringField(max_length=30)
    password = db.StringField(max_length=50)
    create_datetime = db.DateTimeField(default=dte.now)
    is_switch = db.IntField()
    yh_type = db.StringField(default="BOCB2C")
    source_include = db.ListField(default=["yhzf", "zfb"])        # 该用户处理的源站
    is_close = db.BooleanField(default=False)
    is_removed = db.IntField(default=0)

    meta = {
        "indexes": [
            "username",
            "is_switch",
            "is_removed",
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

    @property
    def is_superuser(self):
        if self.username in ["luojunping", "xiangleilei", "liuquan", "luocky", "august"]:
            return True
        return False


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
    source_weight = db.DictField()          # 源站分配权重
    source_order_limit = db.DictField()     # 源站分配单数限制
    dest_list = db.ListField()              # 目的地列表  ["成都|cd", "重庆|cq"]

    meta = {
        "indexes": [
            "province",
            "city_name",
            "crawl_source",
            "is_active",
        ],
    }

    def check_new_dest(self):
        qs = Line.objects.filter(s_province=self.province, s_city_name__startswith=self.city_name) \
                         .aggregate({
                             "$group": {
                                 "_id": {
                                     "city_name": "$d_city_name",
                                     "city_code": "$d_city_code"
                                 }
                             }
                         })
        old = set(self.dest_list)
        new = set(map(lambda x: "%s|%s" %
                      (x["_id"]["city_name"], x["_id"]["city_code"]), qs))
        self.modify(dest_list=old.union(new))


class Line(db.Document):
    """线路表"""
    line_id = db.StringField(unique=True)           # 路线id, 必须唯一
    crawl_source = db.StringField(required=True)    # 爬取来源
    compatible_lines = db.DictField()               # 兼容的路线

    # starting
    s_province = db.StringField(required=True)      # 出发省(必须有值)
    s_city_id = db.StringField()                    # 出发城市id（可为空）
    s_city_name = db.StringField(required=True)     # 出发城市名字(必须有值
    s_sta_name = db.StringField(required=True)      # 出发站名字（必须有值)
    s_sta_id = db.StringField()                     # 出发站id(可为空)
    s_city_code = db.StringField(required=True)     # 出发城市拼音缩写(必须有值)

    # destination
    d_city_name = db.StringField(required=True)     # 目的地城市名字(必须有值)
    d_city_id = db.StringField()                    # 目的地城市id(可为空)
    d_city_code = db.StringField(required=True)     # 目的地城市拼音缩写(必须有值)
    d_sta_name = db.StringField(required=True)      # 目的地站名字(必须有值)
    d_sta_id = db.StringField()                     # 目的地站id(可为空)

    drv_date = db.StringField(required=True)        # 开车日期 yyyy-MM-dd (必须有值)
    drv_time = db.StringField(required=True)        # 开车时间 hh:mm (必须有值)
    drv_datetime = db.DateTimeField()               # DateTime类型的开车时间 (必须有值)
    distance = db.StringField()                     # 行程距离(可为空)
    vehicle_type = db.StringField()                 # 车型(可为空), eg:大型大巴
    seat_type = db.StringField()                    # 座位类型(不重要)
    bus_num = db.StringField(required=True)         # 车次(必须有值)
    full_price = db.FloatField()                    # 票价(必须有值)
    half_price = db.FloatField()                    # 儿童价(不重要)
    fee = db.FloatField()                           # 手续费
    crawl_datetime = db.DateTimeField()             # 爬取的时间
    extra_info = db.DictField()                     # 额外信息字段
    left_tickets = db.IntField()                    # 剩余票数
    update_datetime = db.DateTimeField()            # 更新时间
    refresh_datetime = db.DateTimeField()           # 余票刷新时间
    shift_id = db.StringField()                     # 车次(不重要)

    meta = {
        "indexes": [
            "line_id",
            "s_province",
            "s_sta_name",
            "s_city_name",
            "d_city_name",
            "d_city_code",
            "d_sta_name",
            "crawl_source",
            "bus_num",
            "drv_date",
            "drv_time",
            "drv_datetime",
            ("s_city_name", "d_city_name", "drv_date", "crawl_source"),
            {
                'fields': ['crawl_datetime'],
                'expireAfterSeconds': 3600 * 24 * 20,       # 20天
            }
        ],
    }

    def get_open_city(self):
        city = self.s_city_name
        if city in CITY_NAME_TRANS:
            city = CITY_NAME_TRANS[city]
        elif len(city) > 2 and (city.endswith("市") or city.endswith("县")):
            city = city[:-1]
        try:
            open_city = OpenCity.objects.get(city_name=city)
            return open_city
        except OpenCity.DoesNotExist:
            line_log.error(
                "[opencity] %s %s not matched open city", self.line_id, city)
            return None

    def __str__(self):
        return "[Line object %s]" % self.line_id

    def real_price(self):
        return self.fee + self.full_price

    def get_json(self):
        """
        传给客户端的格式和数据，不能轻易修改！
        """
        delta = self.drv_datetime - dte.now()
        left_tickets = self.left_tickets
        if delta.total_seconds < 40 * 60:
            left_tickets = 0
        return {
            "line_id": self.line_id,
            "starting_city": self.s_city_name,
            "starting_station": self.s_sta_name,
            "destination_city": self.d_city_name,
            "destination_station": self.d_sta_name,
            "bus_num": self.bus_num if self.crawl_source != 'kuaiba' else self.bus_num[-5:],
            "drv_date": self.drv_date,
            "drv_time": self.drv_time,
            "vehicle_type": self.vehicle_type,
            "full_price": self.full_price,
            "half_price": self.half_price,
            "left_tickets": left_tickets,
            "fee": self.fee,
            "distance": self.distance,
        }

    def check_compatible_lines(self, reload=False):
        if not reload and self.compatible_lines:
            return self.compatible_lines
        if self.s_province == "重庆":
            # 重庆省网，方便网
            if self.crawl_source == SOURCE_CQKY:
                trans = {"重庆主城": "重庆"}
                tar_source = SOURCE_FB
            elif self.crawl_source == SOURCE_FB:
                trans = {"重庆": "重庆主城"}
                tar_source = SOURCE_CQKY
            try:
                ob = Line.objects.get(crawl_source=tar_source,
                                      s_city_name=trans.get(
                                          self.s_city_name, self.s_city_name),
                                      d_city_name=trans.get(
                                          self.d_city_name, self.d_city_name),
                                      s_sta_name=self.s_sta_name,
                                      d_sta_name=self.d_sta_name,
                                      drv_datetime=self.drv_datetime)
                self.modify(compatible_lines={
                            self.crawl_source: self.line_id, tar_source: ob.line_id})
            except Line.DoesNotExist:
                self.modify(compatible_lines={self.crawl_source: self.line_id})
            return self.compatible_lines
        elif self.s_province == "江苏":
            # 方便网，车巴达，江苏省网, 同程
            trans = {}
            qs = Line.objects.filter(s_city_name=trans.get(self.s_city_name, self.s_city_name),
                                     d_city_name=trans.get(
                                         self.d_city_name, self.d_city_name),
                                     s_sta_name=self.s_sta_name,
                                     d_sta_name=self.d_sta_name,
                                     drv_datetime=self.drv_datetime)
            d_line = {obj.crawl_source: obj.line_id for obj in qs}
            d_line.update({self.crawl_source: self.line_id})
            self.modify(compatible_lines=d_line)
            return self.compatible_lines
        elif self.s_province == "四川":
            # 四川汽车票务网, 方便网
            # 方便网和四川目的地城市差别太多，所以不匹配目的地城市
            s_city = self.s_city_name.rstrip("市")
            qs = Line.objects.filter(s_sta_name=self.s_sta_name,
                                     s_city_name__startswith=unicode(s_city),
                                     d_sta_name=self.d_sta_name,
                                     bus_num=self.bus_num,
                                     drv_datetime=self.drv_datetime)
            d_line = {obj.crawl_source: obj.line_id for obj in qs}
            d_line.update({self.crawl_source: self.line_id})
            self.modify(compatible_lines=d_line)
            return self.compatible_lines
        elif self.s_province == "北京":
            s_sta_name = self.s_sta_name
            if self.crawl_source == SOURCE_CTRIP:
                if s_sta_name != u'首都机场站':
                    s_sta_name = self.s_sta_name.decode(
                        "utf-8").strip().rstrip(u"客运站")
            qs = Line.objects.filter(
                s_city_name=self.s_city_name,
                s_sta_name__startswith=unicode(s_sta_name),
                d_city_name=self.d_city_name,
                #                                      d_sta_name=self.d_sta_name,
                full_price=self.full_price,
                #                                      bus_num=self.bus_num,
                drv_datetime=self.drv_datetime)
            d_line = {obj.crawl_source: obj.line_id for obj in qs}
            d_line.update({self.crawl_source: self.line_id})
            self.modify(compatible_lines=d_line)
            return self.compatible_lines
        else:
            qs = Line.objects.filter(s_sta_name=self.s_sta_name,
                                     s_city_name=self.s_city_name,
                                     d_sta_name=self.d_sta_name,
                                     d_city_name=self.d_city_name,
                                     bus_num=self.bus_num,
                                     drv_datetime=self.drv_datetime)
            d_line = {obj.crawl_source: obj.line_id for obj in qs}
            d_line.update({self.crawl_source: self.line_id})
            self.modify(compatible_lines=d_line)
            return self.compatible_lines

    def refresh(self, force=False):
        from app.flow import get_flow
        flow = get_flow(self.crawl_source)
        return flow.refresh_line(self, force=force)


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
    ticket_price = db.FloatField()          # 单张车票价格
    ticket_amount = db.IntField()
    ticket_fee = db.FloatField()            # 单张车票手续费
    drv_datetime = db.DateTimeField()       # DateTime类型的开车时间
    bus_num = db.StringField()              # 班次
    starting_name = db.StringField()        # 出发地
    destination_name = db.StringField()     # 目的地

    # 支付信息
    pay_trade_no = db.StringField()  # 支付交易号
    refund_trade_no = db.StringField()  # 退款交易流水号
    pay_order_no = db.StringField()  # 源站传给支付宝的商户订单号
    pay_money = db.FloatField()     # 实际支付的金额
    pay_url = db.StringField()      # 支付链接
    pay_status = db.IntField(default=PAY_STATUS_NONE)   # 支付状态
    pay_channel = db.StringField()  # 支付渠道, wy-网银 wx-微信 alipay-支付宝
    pay_account = db.StringField()  # 支付账号
    refund_money = db.FloatField()   # 退款金额

    # 乘客和联系人信息
    # 包含字段: name, telephone, id_type,id_number,age_level
    contact_info = db.DictField()
    riders = db.ListField(db.DictField())

    # 锁票信息: 源网站在锁票这步返回的数据
    lock_datetime = db.DateTimeField()
    lock_info = db.DictField()

    # 取票信息
    pick_code_list = db.ListField(db.StringField(max_length=100))     # 取票密码
    # 取票说明, len(pick_code_list)必须等于len(pick_msg_list)
    pick_msg_list = db.ListField(db.StringField(max_length=300))

    # 回调地址
    locked_return_url = db.URLField()   # 锁票成功回调
    issued_return_url = db.URLField()   # 出票成功回调

    # 源站账号
    source_account = db.StringField()
    crawl_source = db.StringField()     # 源网站
    extra_info = db.DictField()         # 额外信息

    # 代购人员信息
    kefu_username = db.StringField()
    kefu_order_status = db.IntField()   # 1表示已处理
    kefu_updatetime = db.DateTimeField()
    kefu_assigntime = db.DateTimeField()

    # 跟踪纪录
    trace_list = db.ListField(db.ReferenceField("OrderTrace"))
    yc_status = db.IntField(default=0)

    meta = {
        "indexes": [
            "order_no",
            "out_order_no",
            "raw_order_no",
            "status",
            "crawl_source",
            "create_date_time",
            "source_account",
            "kefu_username",
            "yc_status",
        ],
    }

    @property
    def need_send_msg(self):
        if self.status in [STATUS_GIVE_BACK, STATUS_LOCK_FAIL, STATUS_ISSUE_FAIL]:
            return 1
        if self.crawl_source in [SOURCE_BUS365, SOURCE_TC]:
            return 0
        return 1

    def __str__(self):
        return "[Order object %s]" % self.order_no

    def log_name(self):
        return "%s %s" % (self.crawl_source, self.order_no)

    def change_lock_rebot(self):
        """
        更换锁票账号
        """
        rebot_cls = None
        for cls in get_rebot_class(self.crawl_source):
            if cls.is_for_lock:
                rebot_cls = cls
                break
        try:
            rebot = rebot_cls.objects.get(telephone=self.source_account)
        except rebot_cls.DoesNotExist:
            rebot = None

        if self.status not in [STATUS_WAITING_LOCK, STATUS_LOCK_RETRY]:
            return rebot
        old = self.source_account
        self.modify(source_account="")
        with rebot_cls.get_and_lock(self) as newrebot:
            self.modify(source_account=newrebot.telephone)
            new = self.source_account
            rebot_log.info(
                "[change_lock_rebot] succ. order: %s %s => %s", self.order_no, old, new)
            return newrebot

    @property
    def source_account_pass(self):
        accounts = SOURCE_INFO[self.crawl_source]["accounts"]
        return accounts.get(self.source_account, [""])[0]

    def get_lock_rebot(self):
        """
        获取用于锁票的rebot
        """
        cls_lst = get_rebot_class(self.crawl_source)
        rebot_cls = None
        for cls in cls_lst:
            if cls.is_for_lock:
                rebot_cls = cls
                break
        try:
            rebot_log.info(rebot_cls.objects.get(
                telephone=self.source_account))
            return rebot_cls.objects.get(telephone=self.source_account)
        except rebot_cls.DoesNotExist:
            return self.change_lock_rebot()

    def complete_by(self, user_obj):
        self.kefu_order_status = 1
        self.kefu_updatetime = dte.now()
        self.kefu_username = user_obj.username
        self.modify(kefu_order_status=1,
                    kefu_updatetime=dte.now(),
                    kefu_username=user_obj.username)
        assign.remove_dealing(self, user_obj)
        assign.add_dealed_but_not_issued(self, user_obj)

    def on_create(self, reason=""):
        if self.status != STATUS_WAITING_LOCK:
            return
        desc = "订单创建成功 12308订单号:%s" % self.out_order_no
        self.add_trace(OT_CREATED, desc)

    def on_lock_fail(self, reason=""):
        if self.status != STATUS_LOCK_FAIL:
            return
        desc = "锁票失败 %s" % reason
        self.add_trace(OT_LOCK_FAIL, desc)

    def on_lock_success(self, reason=""):
        if self.status != STATUS_WAITING_ISSUE:
            return
        desc = "锁票成功 源站订单号:%s" % self.raw_order_no
        self.add_trace(OT_LOCK_SUCC, desc)

        from tasks import async_refresh_order
        async_refresh_order.apply_async((self.order_no,), countdown=10)

    def on_lock_retry(self, reason=""):
        if self.status != STATUS_LOCK_RETRY:
            return
        desc = "锁票重试 原因：%s" % reason
        self.add_trace(OT_LOCK_RETRY, desc)

    def on_give_back(self, reason=""):
        if self.status != STATUS_GIVE_BACK:
            return
        self.add_trace(OT_ISSUE_FAIL, "出票失败 原因：源站已退款")

        r = getRedisObj()
        key = RK_ISSUE_FAIL_COUNT % self.crawl_source
        r.delete(key)

    def on_issue_fail(self, reason=""):
        if self.status != STATUS_ISSUE_FAIL:
            return
        self.add_trace(OT_ISSUE_FAIL, "出票失败 原因：%s" % reason)

        from tasks import issue_fail_send_email
        r = getRedisObj()
        key = RK_ISSUE_FAIL_COUNT % self.crawl_source
        r.sadd(key, self.order_no)
        order_ct = r.scard(key)
        if order_ct > ISSUE_FAIL_WARNING:
            issue_fail_send_email.delay(key)

    def on_issueing(self, reason=""):
        if self.status != STATUS_ISSUE_ING:
            return
        self.add_trace(OT_ISSUE_ING, "正在出票")

        r = getRedisObj()
        key = RK_ISSUEING_COUNT
        r.sadd(key, self.order_no)

    def on_issue_success(self, reason=""):
        if self.status != STATUS_ISSUE_SUCC:
            return
        self.add_trace(OT_ISSUE_SUCC, "出票成功 短信：%s" % self.pick_msg_list[0])

        r = getRedisObj()
        key = RK_ISSUE_FAIL_COUNT % self.crawl_source
        r.delete(key)
        key = RK_ISSUEING_COUNT
        r.delete(key)

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

    def refresh_status(self, force=False):
        from app.flow import get_flow
        flow = get_flow(self.crawl_source)
        return flow.refresh_issue(self, force=force)

    def add_trace(self, ttype, desc, extra_info={}):
        ot = OrderTrace(order_no=self.order_no,
                        trace_type=ttype,
                        desc=desc,
                        extra_info=extra_info)
        ot.save()
        self.update(push__trace_list=ot)


class OrderTrace(db.Document):
    """
    订单追踪
    """
    order_no = db.StringField(required=True)
    trace_type = db.IntField()          # 追踪类型
    desc = db.StringField()             # 描述文本
    extra_info = db.DictField()         # 额外信息
    create_datetime = db.DateTimeField(default=dte.now)

    meta = {
        "indexes": [
            "trace_type",
            "order_no",
        ],
    }

    @property
    def trace_type_msg(self):
        return OT_MSG.get(self.trace_type, "其他")


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

    crawl_source = ""
    is_for_lock = False         # 是否为用于发起锁票的账号

    def __str__(self):
        return self.telephone

    @property
    def proxy_ip(self):
        rds = get_redis("default")
        ipstr = self.ip
        key = "proxy:%s" % self.crawl_source
        if ipstr and rds.sismember(key, ipstr):
            return ipstr
        ipstr = rds.srandmember(key)
        self.modify(ip=ipstr)
        return ipstr

    @classmethod
    def login_all(cls):
        # 登陆所有预设账号
        has_checked = {}
        accounts = SOURCE_INFO[cls.crawl_source]["accounts"]
        for bot in cls.objects:
            has_checked[bot.telephone] = 1
            if bot.telephone not in accounts:
                bot.modify(is_active=False)
                continue
            pwd, _ = accounts[bot.telephone]
            bot.modify(password=pwd)
            msg = bot.login()
            rebot_log.info("[login_all] %s %s %s",
                           cls.crawl_source, bot.telephone, msg)

        for tele, (pwd, openid) in accounts.items():
            if tele in has_checked:
                continue
            bot = cls(is_active=True,
                      is_locked=False,
                      telephone=tele,
                      password=pwd,)
            bot.save()
            msg = bot.login()
            rebot_log.info("[login_all] %s %s %s",
                           cls.crawl_source, bot.telephone, msg)

    @classmethod
    def get_one(cls, order=None):
        sta_bind = SOURCE_INFO[cls.crawl_source].get("station_bind", {})
        city_bind = SOURCE_INFO[cls.crawl_source].get("city_bind", {})
        query = {}
        if order and sta_bind:
            s_sta_name = order.starting_name.split(";")[1]
            if s_sta_name in sta_bind:
                query.update(telephone__in=sta_bind[s_sta_name])
        elif order and city_bind:
            s_city_name = order.starting_name.split(";")[0]
            if s_city_name in city_bind:
                query.update(telephone__in=city_bind[s_city_name])

        qs = cls.objects.filter(is_active=True, is_locked=False)
        if not qs:
            return
        sub_qs = qs.filter(**query)
        if sub_qs:
            qs = sub_qs
        size = qs.count()
        rd = random.randint(0, size - 1)
        return qs[rd]

    @classmethod
    @contextmanager
    def get_and_lock(cls, order):
        # 检查释放被锁的账号
        for rebot in cls.objects.filter(is_locked=True, is_active=True):
            for no in rebot.doing_orders.keys():
                try:
                    tmp_order = Order.objects.get(order_no=no)
                except:
                    tmp_order = None
                if tmp_order:
                    if tmp_order.status in [STATUS_ISSUE_FAIL, STATUS_ISSUE_SUCC, STATUS_LOCK_FAIL, STATUS_GIVE_BACK]:
                        rebot.remove_doing_order(tmp_order)

        if order.source_account:
            obj = cls.objects.get(telephone=order.source_account)
        else:
            obj = cls.get_one(order=order)
        if obj:
            obj.add_doing_order(order)
            rebot_log.info(
                "[get_and_lock] succ. tele: %s, order: %s", obj.telephone, order.order_no)
        else:
            rebot_log.info("[get_and_lock] fail. order: %s", order.order_no)
        try:
            yield obj
        except Exception, e:
            if obj:
                obj.remove_doing_order(order)
            raise e

    @classmethod
    def get_lock_one(cls, order):
        """
        后面会逐步替代get_and_lock
        """
        # 检查释放被锁的账号
        for rebot in cls.objects.filter(is_locked=True, is_active=True):
            for no in rebot.doing_orders.keys():
                try:
                    tmp_order = Order.objects.get(order_no=no)
                except:
                    tmp_order = None
                if tmp_order:
                    if tmp_order.status in [STATUS_ISSUE_FAIL, STATUS_ISSUE_SUCC, STATUS_LOCK_FAIL, STATUS_GIVE_BACK]:
                        rebot.remove_doing_order(tmp_order)

        if order.source_account:
            obj = cls.objects.get(telephone=order.source_account)
        else:
            obj = cls.get_one(order=order)
        if obj:
            obj.add_doing_order(order)
        return obj

    def add_doing_order(self, order):
        order.modify(source_account=self.telephone)
        d = self.doing_orders
        if order.order_no in d:
            return
        d[order.order_no] = 1
        self.modify(doing_orders=d)
        self.on_add_doing_order(order)

    def remove_doing_order(self, order):
        rebot_log.info("[remove_doing_order] %s order: %s account: %s %s",
                       self.crawl_source, order.order_no, self.telephone, self.doing_orders)
        d = self.doing_orders
        if order.order_no in d:
            del d[order.order_no]
            self.modify(doing_orders=d)
            self.on_remove_doing_order(order)

    def on_add_doing_order(self, order):
        pass

    def on_remove_doing_order(self, order):
        pass

    def test_login_status(self):
        """
        验证此账号是否已经登录
        """
        raise Exception("Not Implemented")

    def login(self):
        """
        登录成功返回"OK", 失败返回其他字符串。
        """
        raise Exception("Not Implemented")

    def http_get(self, url, **kwargs):
        retry = 1
        for i in range(retry):  # 重试retry次
            if self.proxy_ip:
                kwargs["proxies"] = {"http": "http://%s" % self.proxy_ip}
            if "timeout" not in kwargs:
                kwargs["timeout"] = 30
            try:
                r = requests.get(url, **kwargs)
            except Exception, e:
                if hasattr(self, "ip"):
                    self.modify(ip="")
                if i >= retry - 1:
                    raise e
                continue
            return r

    def http_post(self, url, **kwargs):
        retry = 1
        for i in range(retry):  # 重试retry次
            if self.proxy_ip:
                kwargs["proxies"] = {"http": "http://%s" % self.proxy_ip}
            if "timeout" not in kwargs:
                kwargs["timeout"] = 30
            try:
                r = requests.post(url, **kwargs)
            except Exception, e:
                if hasattr(self, "ip"):
                    self.modify(ip="")
                if i >= retry - 1:
                    raise e
                continue
            return r

# 代理ip, is_locked
class Hn96520WebRebot(Rebot):
    user_agent = db.StringField()
    cookies = db.StringField()
    # ip = db.StringField(default="")
    # indexes索引, 'collections'
    meta = {
        "indexes": ["telephone", "is_active", "is_locked"],
        "collection": "hn96520web_rebot",
    }
    crawl_source = SOURCE_HN96520
    is_for_lock = True

    # @property
    # def proxy_ip(self):
    #     return ''
    #     rds = get_redis("default")
    #     ipstr = self.ip
    #     key = RK_PROXY_IP_WXSZ
    #     if ipstr and rds.sismember(key, ipstr):
    #         return ipstr
    #     ipstr = rds.srandmember(key)
    #     self.modify(ip=ipstr)
    #     return ipstr
    def clear_riders(self, riders={}):
        # 默认的不能删除
        is_login = self.test_login_status()
        if not is_login:
            return
        headers = {"User-Agent": self.user_agent}
        cookies = json.loads(self.cookies)
        rider_url = 'http://www.hn96520.com/member/modify.aspx'
        r = requests.get(rider_url, headers=headers, cookies=cookies)
        soup = BeautifulSoup(r.content, 'lxml')
        info = soup.find('table', attrs={'class': 'tblp shadow', 'style': True}).find_all('tr', attrs={'id': True})
        for x in info:
            uid = x.get('id').strip()
            uid = str(re.search(r'\d+', uid).group(0))
            if uid in riders.values() or not riders:
                delurl = 'http://www.hn96520.com/member/takeman.ashx?action=DeleteTakeman&id={0}&memberid={1}'.format(uid, self.memid)
                requests.get(delurl, headers=headers, cookies=cookies)

    def add_riders(self, order):
        id_lst = {}
        is_login = self.test_login_status()
        if not is_login:
            pass
        riders = order.riders
        headers = {'User-Agent': self.user_agent}
        cookies = json.loads(self.cookies)
        for rider in riders:
            name = rider.get('name', '')
            cardid = rider.get('id_number', '')
            sel = rider.get('telephone', '')
            addurl = 'http://www.hn96520.com/member/takeman.ashx?action=AppendTakeman&memberid={0}&name={1}&cardid={2}&sel={3}'.format(self.memid, name, cardid, sel)
            # rebot_log.info(addurl)
            # rebot_log.info(headers)
            r = requests.get(addurl, headers=headers, cookies=cookies)
            if r.content != '0':
                id_lst['cardid'] = r.content
                # rebot_log.info('添加乘客 => {0}'.format(name))
            else:
                pass
        return id_lst
    # def check_code_status(self, code):
    #     rebot_log.info('code is {0}'.format(code))
    #     url = 'http://www.hn96520.com/member/ajax/checkcode.aspx?code={0}'.format(code)
    #     headers = {'User-Agent': self.user_agent}
    #     cookies = json.loads(self.cookies)
    #     r = requests.get(url, headers=headers, cookies=cookies)
    #     rebot_log.info(code)
    #     rebot_log.info(dict(r.cookies))
    #     if 'true' in r.content:
    #         return 1
    #     else:
    #         return 0

    def test_login_status(self):
        # self.is_locked = True
        # self.save()
        undone_order_url = "http://www.hn96520.com/member/modify.aspx"
        headers = {"User-Agent": self.user_agent}
        try:
            cookies = json.loads(self.cookies)
        except:
            cookies = ''
        r = requests.get(undone_order_url, headers=headers, cookies=cookies)
        soup = BeautifulSoup(r.content, "lxml")
        try:
            memid = soup.find('a', attrs={'id': re.compile(r"\w\d+")}).get('href', '')
            memid = re.findall(r'\d+', memid)[-1]
        except:
            memid = 0
        if memid:
            self.memid = memid
            self.save()
            rebot_log.info(memid)
            cookies.update(r.cookies)
            # rebot_log.info('成功登录 tel {0}'.format(tel))
            return 1
        else:
            # rebot_log.info('fail登录 tel {0}'.format(tel))
            return 0

    # 初始化帐号

    def login(self):
        ua = random.choice(BROWSER_USER_AGENT)
        self.last_login_time = dte.now()
        self.user_agent = ua
        self.is_active = True
        self.cookies = "{}"
        self.save()
        rebot_log.info("创建成功 %s", self.telephone)
        return "OK"


class CcwWebRebot(Rebot):
    user_agent = db.StringField()
    cookies = db.StringField()
    # ip = db.StringField(default="")
    # indexes索引, 'collections'
    meta = {
        "indexes": ["telephone", "is_active", "is_locked"],
        "collection": "ccwweb_rebot",
    }
    crawl_source = SOURCE_CCW
    is_for_lock = True

    # @property
    # def proxy_ip(self):
    #     return ''
    #     rds = get_redis("default")
    #     ipstr = self.ip
    #     key = RK_PROXY_IP_WXSZ
    #     if ipstr and rds.sismember(key, ipstr):
    #         return ipstr
    #     ipstr = rds.srandmember(key)
    #     self.modify(ip=ipstr)
    #     return ipstr
    def clear_riders(self, riders={}):
        # 默认的不能删除
        is_login = self.test_login_status()
        if not is_login:
            return
        headers = {"User-Agent": self.user_agent}
        cookies = json.loads(self.cookies)
        rider_url = 'http://www.hn96520.com/member/modify.aspx'
        r = requests.get(rider_url, headers=headers, cookies=cookies)
        soup = BeautifulSoup(r.content, 'lxml')
        info = soup.find('table', attrs={'class': 'tblp shadow', 'style': True}).find_all('tr', attrs={'id': True})
        for x in info:
            uid = x.get('id').strip()
            uid = str(re.search(r'\d+', uid).group(0))
            if uid in riders.values() or not riders:
                delurl = 'http://www.hn96520.com/member/takeman.ashx?action=DeleteTakeman&id={0}&memberid=449606'.format(uid)
                requests.get(delurl, headers=headers, cookies=cookies)

    def add_riders(self, order):
        id_lst = {}
        is_login = self.test_login_status()
        if not is_login:
            pass
        riders = order.riders
        headers = {'User-Agent': self.user_agent}
        cookies = json.loads(self.cookies)
        for rider in riders:
            name = rider.get('name', '')
            cardid = rider.get('id_number', '')
            sel = rider.get('telephone', '')
            addurl = 'http://www.hn96520.com/member/takeman.ashx?action=AppendTakeman&memberid=449606&name={0}&cardid={1}&sel={2}'.format(name, cardid, sel)
            # rebot_log.info(addurl)
            # rebot_log.info(headers)
            r = requests.get(addurl, headers=headers, cookies=cookies)
            if r.content != '0':
                id_lst['cardid'] = r.content
                # rebot_log.info('添加乘客 => {0}'.format(name))
            else:
                pass
        return id_lst
    # def check_code_status(self, code):
    #     rebot_log.info('code is {0}'.format(code))
    #     url = 'http://www.hn96520.com/member/ajax/checkcode.aspx?code={0}'.format(code)
    #     headers = {'User-Agent': self.user_agent}
    #     cookies = json.loads(self.cookies)
    #     r = requests.get(url, headers=headers, cookies=cookies)
    #     rebot_log.info(code)
    #     rebot_log.info(dict(r.cookies))
    #     if 'true' in r.content:
    #         return 1
    #     else:
    #         return 0

    def test_login_status(self):
        # self.is_locked = True
        # self.save()
        undone_order_url = "http://www.chechuw.com/UserCenter/userDataEdit"
        headers = {"User-Agent": self.user_agent}
        try:
            cookies = json.loads(self.cookies)
        except:
            cookies = ''
        r = requests.get(undone_order_url, headers=headers, cookies=cookies)
        soup = BeautifulSoup(r.content, "lxml")
        try:
            tel = soup.find(
                'input', attrs={'id': 'telphone', 'class': 'text'}).get('value')
        except:
            tel = 0
        if tel:
            cookies.update(r.cookies)
            # rebot_log.info('成功登录 tel {0}'.format(tel))
            return 1
        else:
            # rebot_log.info('fail登录 tel {0}'.format(tel))
            return 0

    # 初始化帐号

    def login(self):
        ua = random.choice(BROWSER_USER_AGENT)
        self.last_login_time = dte.now()
        self.user_agent = ua
        self.is_active = True
        self.cookies = "{}"
        self.save()
        rebot_log.info("创建成功 %s", self.telephone)
        return "OK"


class CyjtWebRebot(Rebot):
    user_agent = db.StringField()
    cookies = db.StringField()
    meta = {
        "indexes": ["telephone", "is_active", "is_locked"],
        "collection": "cyjtweb_rebot",
    }
    crawl_source = SOURCE_CYJT
    is_for_lock = True

    def clear_riders(self, riders={}):
        pass

    def add_riders(self, order):
        id_lst = {}
        is_login = self.test_login_status()
        if not is_login:
            pass
        riders = order.riders
        headers = {'User-Agent': self.user_agent}
        cookies = json.loads(self.cookies)
        for rider in riders:
            name = rider.get('name', '')
            cardid = rider.get('id_number', '')
            sel = rider.get('telephone', '')
            addurl = 'http://www.hn96520.com/member/takeman.ashx?action=AppendTakeman&memberid={0}&name={1}&cardid={2}&sel={3}'.format(self.memid, name, cardid, sel)
            # rebot_log.info(addurl)
            # rebot_log.info(headers)
            r = requests.get(addurl, headers=headers, cookies=cookies)
            if r.content != '0':
                id_lst['cardid'] = r.content
                # rebot_log.info('添加乘客 => {0}'.format(name))
            else:
                pass
        return id_lst

    def test_login_status(self):
        pass

    # 初始化帐号

    def login(self):
        ua = random.choice(BROWSER_USER_AGENT)
        self.last_login_time = dte.now()
        self.user_agent = ua
        self.is_active = True
        self.cookies = "{}"
        self.save()
        rebot_log.info("创建成功 %s", self.telephone)
        return "OK"


class TzkyWebRebot(Rebot):
    user_agent = db.StringField()
    cookies = db.StringField(default="{}")
    ip = db.StringField()

    meta = {
        "indexes": ["telephone", "is_active", "is_locked"],
        "collection": "tzkyweb_rebot",
    }
    crawl_source = SOURCE_TZKY
    is_for_lock = True

    @property
    def proxy_ip(self):
        return ""

    def login(self):
        if self.test_login_status():
            return "OK"

        url = "http://www.tzfeilu.com:8086/index.php/login/index"
        ua = random.choice(BROWSER_USER_AGENT)
        headers = {"User-Agent": ua}
        r = self.http_get(url, headers=headers)
        cookies = dict(r.cookies)
        params = {
            "ispost": 1,
            "username": self.telephone,
            "password": self.password,
        }

        headers["Content-Type"] = "application/x-www-form-urlencoded"
        r = self.http_post(url,
                           data=urllib.urlencode(params),
                           headers=headers, cookies=cookies)
        soup = BeautifulSoup(r.content, "lxml")
        tel = soup.select_one("#login_user").text
        if tel == self.telephone:
            r_cookies = dict(r.cookies)
            cookies.update(r_cookies)
            self.last_login_time = dte.now()
            self.user_agent = ua
            self.is_active = True
            self.cookies = json.dumps(cookies)
            self.save()
            return "OK"
        else:
            self.update(cookies="{}")
            return "fail"

    def test_login_status(self):
        user_url = "http://www.tzfeilu.com:8086/index.php/profile/index"
        headers = {"User-Agent": self.user_agent}
        r = self.http_get(user_url, headers=headers,
                          cookies=json.loads(self.cookies))
        parse = urllib2.urlparse.urlparse(r.url)
        if u"login" in parse.path:
            return 0
        return 1


class WxszRebot(Rebot):
    user_agent = db.StringField(
        default="Apache-HttpClient/UNAVAILABLE (java 1.4)")
    uid = db.StringField()
    sign = db.StringField()
    ip = db.StringField(default="")

    meta = {
        "indexes": ["telephone", "is_active", "is_locked"],
        "collection": "wxsz_rebot",
    }
    crawl_source = SOURCE_WXSZ
    is_for_lock = True

    @property
    def proxy_ip(self):
        rds = get_redis("default")
        ipstr = self.ip
        key = RK_PROXY_IP_WXSZ
        if ipstr and rds.sismember(key, ipstr):
            return ipstr
        ipstr = rds.srandmember(key)
        self.modify(ip=ipstr)
        return ipstr

    def login(self):
        if self.test_login_status():
            rebot_log.info("已经登陆wxsz %s" % self.telephone)
            return "OK"
        url = "http://content.2500city.com/ucenter/user/login"
        params = dict(
            account=self.telephone,
            platform="2",
            password=SOURCE_INFO[SOURCE_WXSZ]["pwd_encode"][self.password],
            appVersion="3.9.1",
            deviceId="",
            version="3.9.1",
        )
        url = "%s?%s" % (url, urllib.urlencode(params))
        r = self.http_get(url, headers={"User-Agent": self.user_agent})
        res = r.json()
        error = res["errorMsg"]
        if not error:
            _, sign = SOURCE_INFO[SOURCE_WXSZ]["accounts"][self.telephone]
            self.modify(uid=res["data"]["uid"], sign=sign)
            return "OK"
        rebot_log.info("登陆失败wxsz %s %s", self.telephone, error)
        return "fail"

    def test_login_status(self):
        user_url = "http://content.2500city.com/ucenter/user/getuserinfo"
        params = {
            "sign": self.sign,
            "uid": self.uid,
        }
        headers = {
            "User-Agent": self.user_agent,
            "Content-Type": "application/json;charset=UTF-8",
        }
        r = self.http_post(user_url, headers=headers, data=json.dumps(params))
        try:
            res = r.json()
        except:
            return 0
        if res["errorCode"] != 0:
            return 0
        if res["data"]["mobile"] != self.telephone:
            return 0
        return 1

    def clear_riders(self):
        is_login = self.test_login_status()
        if not is_login:
            return
        headers = {
            "User-Agent": self.user_agent,
            "Content-Type": "application/x-www-form-urlencoded"
        }
        query_url = "http://coach.wisesz.mobi/coach_v38/contacts/index"
        params = {"sign": self.sign, "uid": self.uid}
        r = self.http_post(query_url, headers=headers,
                           data=urllib.urlencode(params))
        res = r.json()

        del_url = "http://coach.wisesz.mobi/coach_v38/contacts/ondel"
        for d in res["data"]["dataList"]:
            params = {"sign": self.sign, "id": d["id"], "uid": self.uid}
            self.http_post(del_url, headers=headers,
                           data=urllib.urlencode(params))

    def get_riders(self):
        if not self.test_login_status():
            raise Exception("%s账号未登录" % self.telephone)
        headers = {
            "User-Agent": self.user_agent,
            "Content-Type": "application/x-www-form-urlencoded"
        }
        query_url = "http://coach.wisesz.mobi/coach_v38/contacts/index"
        params = {"sign": self.sign, "uid": self.uid}
        r = self.http_post(query_url, headers=headers,
                           data=urllib.urlencode(params))
        res = r.json()
        card_to_id = {}
        for d in res["data"]["dataList"]:
            card_to_id[d["idcard"]] = d["id"]
        return card_to_id

    def add_riders(self, order):
        add_url = "http://coach.wisesz.mobi/coach_v38/contacts/onadd"
        headers = {
            "User-Agent": self.user_agent,
            "Content-Type": "application/x-www-form-urlencoded"
        }
        id_lst = []
        exists_lst = {}
        for c in order.riders:
            params = {
                "sign": self.sign,
                "uid": self.uid,
                "idcard": c["id_number"],
                "uname": c["name"],
                "tel": c["telephone"] or order.contact_info["telephone"],
            }
            r = self.http_post(add_url, headers=headers,
                               data=urllib.urlencode(params))
            res = r.json()
            if "该身份证号已存在" in res["errorMsg"]:
                if not exists_lst:
                    exists_lst = self.get_riders()
                id_lst.append(exists_lst[c["id_number"].upper()])
            else:
                id_lst.append(res["data"]["id"])
        return id_lst


class ZjgsmWebRebot(Rebot):
    user_agent = db.StringField()
    cookies = db.StringField(default="{}")
    ip = db.StringField(default="")

    meta = {
        "indexes": ["telephone", "is_active", "is_locked"],
        "collection": "zjgsmweb_rebot",
    }
    crawl_source = SOURCE_ZJGSM
    is_for_lock = True

    @classmethod
    def get_one(cls, order=None):
        today = dte.now().strftime("%Y-%m-%d")
        all_accounts = set(cls.objects.filter(
            is_active=True, is_locked=False).distinct("telephone"))
        droped = set()
        for d in Order.objects.filter(status=14,
                                      crawl_source='zjgsm',
                                      create_date_time__gte=today) \
                .aggregate({
                    "$group": {
                        "_id": {"phone": "$source_account"},
                        "count": {"$sum": "$ticket_amount"}}
                }):
            cnt = d["count"]
            phone = d["_id"]["phone"]
            if cnt >= 4:
                droped.add(phone)
        tele = random.choice(list(all_accounts - droped))
        return cls.objects.get(telephone=tele)

    @property
    def proxy_ip(self):
        rds = get_redis("default")
        ipstr = self.ip
        if ipstr and rds.sismember(RK_PROXY_IP_ZJGSM, ipstr):
            return ipstr
        ipstr = rds.srandmember(RK_PROXY_IP_ZJGSM)
        self.modify(ip=ipstr)
        return ipstr

    def test_login_status(self):
        headers = {
            "User-Agent": self.user_agent,
            "Content-Type": "application/x-www-form-urlencoded;charset=UTF-8",
        }
        cookies = json.loads(self.cookies)
        check_url = "http://www.zjgsmwy.com/busticket/busticket/service/Busticket.checkLogin.json"
        r = self.http_post(check_url, headers=headers, cookies=cookies)
        try:
            res = r.json()
        except:
            return 0
        if res["responseData"].get("flag", False):
            return 1
        return 0

    def login(self):
        self.last_login_time = dte.now()
        self.user_agent = random.choice(BROWSER_USER_AGENT)
        self.is_active = True
        self.cookies = "{}"
        self.save()
        return "OK"


class ScqcpAppRebot(Rebot):
    is_encrypt = db.IntField(choices=(0, 1))
    user_agent = db.StringField()
    token = db.StringField()
    open_id = db.StringField()
    ip = db.StringField(default="")

    meta = {
        "indexes": ["telephone", "is_active", "is_locked"],
        "collection": "scqcpapp_rebot",
    }
    crawl_source = SOURCE_SCQCP
    is_for_lock = False

    def on_add_doing_order(self, order):
        self.modify(is_locked=True)

    def on_remove_doing_order(self, order):
        self.modify(is_locked=False)

    @property
    def proxy_ip(self):
        return ""
        # rds = get_redis("default")
        # ipstr = self.ip
        # if ipstr and rds.sismember(RK_PROXY_IP_SCQCP, ipstr):
        #     return ipstr
        # ipstr = rds.srandmember(RK_PROXY_IP_SCQCP)
        # self.modify(ip=ipstr)
        # return ipstr

    @classmethod
    def get_one(cls, order=None):
        city_bind = SOURCE_INFO[cls.crawl_source].get("city_bind", {})
        query = {}
        if order and city_bind:
            s_city_name = order.starting_name.split(";")[0]
            if s_city_name in city_bind:
                query.update(telephone__in=city_bind[s_city_name])
            else:
                init_tel = []
                for _, tel in city_bind.items():
                    init_tel.extend(tel)
                query.update(telephone__nin=init_tel)
        qs = cls.objects.filter(is_active=True, is_locked=False, **query)
        if not qs:
            return
        size = qs.count()
        rd = random.randint(0, size - 1)
        return qs[rd]

    def login(self):
        return
        ua = random.choice(MOBILE_USER_AGENG)
        device = "android" if "android" in ua else "ios"

        # 获取token
        uri = "/api/v1/api_token/get_token_for_app?channel=dxcd&version_code=40&oper_system=%s" % device
        url = urllib2.urlparse.urljoin(SCQCP_DOMAIN, uri)
        headers = {
            "User-Agent": ua,
            "Authorization": self.token,
            "Content-Type": "application/json; charset=UTF-8",
        }
        r = self.http_get(url, headers=headers)
        ret = r.json()
        token = ret["token"]
        self.user_agent = ua
        self.token = token

        is_encrypt = self.is_encrypt or 1
        # 登陆
        uri = "/api/v1/user/login_phone"
        data = {
            "username": self.telephone,
            "password": self.password,
            "is_encrypt": is_encrypt,
        }
        url = urllib2.urlparse.urljoin(SCQCP_DOMAIN, uri)
        headers.update({"Authorization": self.token})
        r = self.http_post(url, data=urllib.urlencode(data), headers=headers)
        ret = r.json()

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
            self.is_encrypt = is_encrypt
            self.save()
            return "OK"

    def test_login_status(self):
        uri = "/scqcp/api/v2/ticket/query_rider"
        check_url = urllib2.urlparse.urljoin(SCQCP_DOMAIN, uri)
        headers = {
            "User-Agent": self.user_agent,
            "Authorization": self.token,
            "Content-Type": "application/json; charset=UTF-8",
        }
        data = {
            "open_id": self.open_id,
        }
        res = self.http_post(
            check_url, data=urllib.urlencode(data), headers=headers)
        ret = res.json()
        if ret['status'] == 1:
            return 1
        return 0


class ScqcpWebRebot(Rebot):
    user_agent = db.StringField()
    cookies = db.StringField(default='{}')
    ip = db.StringField(default="")

    meta = {
        "indexes": ["telephone", "is_active", "is_locked"],
        "collection": "scqcpweb_rebot",
    }
    crawl_source = SOURCE_SCQCP
    is_for_lock = True

    def http_header(self, ua=""):
        return {
            "Charset": "UTF-8",
            "Content-Type": "application/x-www-form-urlencoded; charset=UTF-8",
            "User-Agent": ua or self.user_agent,
        }

    def on_add_doing_order(self, order):
        self.modify(is_locked=True)

    def on_remove_doing_order(self, order):
        self.modify(is_locked=False)

    @property
    def proxy_ip(self):
        return ""
        # rds = get_redis("default")
        # ipstr = self.ip
        # if ipstr and rds.sismember(RK_PROXY_IP_SCQCP, ipstr):
        #     return ipstr
        # ipstr = rds.srandmember(RK_PROXY_IP_SCQCP)
        # self.modify(ip=ipstr)
        # return ipstr

    @classmethod
    def get_one(cls, order=None):
        today = dte.now().strftime("%Y-%m-%d")
        all_accounts = set(cls.objects.filter(
            is_active=True, is_locked=False).distinct("telephone"))
        droped = set()
        for d in Order.objects.filter(status=14,
                                      crawl_source=SOURCE_SCQCP,
                                      create_date_time__gte=today) \
                .aggregate({
                    "$group": {
                        "_id": {"phone": "$source_account"},
                        "count": {"$sum": "$ticket_amount"}}
                }):
            cnt = d["count"]
            phone = d["_id"]["phone"]
            if cnt >= 10:
                droped.add(phone)
        tele = random.choice(list(all_accounts - droped))
        return cls.objects.get(telephone=tele)

    def login(self, valid_code="", token='', headers={}, cookies={}):
        vcode_flag = False
        if not valid_code:
            login_form_url = "http://scqcp.com/login/index.html?%s" % time.time()
            headers = {"User-Agent": random.choice(BROWSER_USER_AGENT)}
            r = self.http_get(login_form_url, headers=headers, cookies=cookies)
            sel = etree.HTML(r.content)
            cookies.update(dict(r.cookies))
            code_url = sel.xpath("//img[@id='txt_check_code']/@src")[0]
            code_url = code_url.split(
                '?')[0] + "?d=0.%s" % random.randint(1, 10000)
            token = sel.xpath("//input[@id='csrfmiddlewaretoken1']/@value")[0]
            r = self.http_get(code_url, headers=headers, cookies=cookies)
            cookies.update(dict(r.cookies))
            valid_code = vcode_scqcp(r.content)
            vcode_flag = True

        if valid_code:
            headers = {
                "User-Agent": headers.get("User-Agent", "") or self.user_agent,
                "Content-Type": "application/x-www-form-urlencoded; charset=UTF-8",
            }
            data = {
                "uname": self.telephone,
                "passwd": self.password,
                "code": valid_code,
                "token": token,
            }
            login_url = "http://scqcp.com/login/check.json"
            r = self.http_post(login_url, data=data,
                               headers=headers, cookies=cookies)
            res = r.json()
            if res["success"]:     # 登陆成功
                cookies.update(dict(r.cookies))
                self.modify(cookies=json.dumps(cookies), is_active=True)
                rebot_log.info("[scqcp]登陆成功, %s vcode_flag:%s",
                               self.telephone, vcode_flag)
                return "OK"
            else:
                msg = res["msg"]
                rebot_log.info("[scqcp]%s %s vcode_flag:%s",
                               self.telephone, msg, vcode_flag)
                if u"验证码不正确" in msg:
                    return "invalid_code"
                return msg
        else:
            ua = random.choice(BROWSER_USER_AGENT)
            self.last_login_time = dte.now()
            self.user_agent = ua
            self.is_active = True
            self.cookies = "{}"
            self.save()
        rebot_log.info("创建成功 %s", self.telephone)
        return "OK"

    def test_login_status(self):
        try:
            #             url = 'http://scqcp.com/login/isLogin.json?r=0.5511045664326151&is_show=no&_=1459936544981'
            headers = self.http_header()
#             res = self.http_post(url, headers=headers, cookies=json.loads(self.cookies))
#             ret = res.json()

            user_url = 'http://scqcp.com/user/get.html?new=0.%s' % random.randint(
                10000000, 100000000000)
            res = self.http_get(user_url, headers=headers,
                                cookies=json.loads(self.cookies))
            result = urlparse.urlparse(res.url)
            if result.path == '/login/index.html':
                return 0
            else:
                content = res.content
                if not isinstance(content, unicode):
                    content = content.decode('utf-8')
                sel = etree.HTML(content)
                telephone = sel.xpath('//*[@id="infoDiv"]/dl/dd[8]/text()')
                if telephone:
                    telephone = telephone[1].replace(
                        '\r\n', '').replace('\t', '').replace(' ', '')
                if self.telephone == telephone:
                    return 1
                else:
                    self.modify(cookies='{}')
                    self.modify(ip="")
                    self.reload()
                    return 0
        except:
            self.modify(cookies='{}')
            self.modify(ip="")
            self.reload()
            return 0


class CBDRebot(Rebot):
    user_agent = db.StringField()
    cookies = db.StringField()
    ip = db.StringField(default="")

    meta = {
        "indexes": ["telephone", "is_active", "is_locked"],
        "collection": "cbd_rebot",
    }
    crawl_source = SOURCE_CBD
    is_for_lock = True

    def test_login_status(self):
        url = "http://m.chebada.com/Order/OrderList"
        headers = {"User-Agent": self.user_agent}
        if not self.cookies:
            return 0
        cookies = json.loads(self.cookies)
        r = requests.get(url, headers=headers, cookies=cookies)
        if u"Account/Login" in r.url:
            return 0
        return 1

    def login(self):
        if self.test_login_status():
            rebot_log.info("已登录cbd %s", self.telephone)
            return "OK"
        from selenium import webdriver
        driver = webdriver.PhantomJS()
        driver.get("http://m.chebada.com/Account/Login")
        token = driver.find_element_by_id("TokenId").get_attribute("value")
        driver.close()

        ua = random.choice(MOBILE_USER_AGENG)
        header = {"User-Agent": ua}
        log_url = "http://m.chebada.com/Account/UserLogin"
        data = {
            "MobileNo": self.telephone,
            "Password": self.password,
            "TokenId": token,
        }
        header["Content-Type"] = "application/x-www-form-urlencoded"
        r = requests.post(log_url, data=urllib.urlencode(data), headers=header)
        ret = r.json()
        if int(ret["response"]["header"]["rspCode"]) == 0:
            self.last_login_time = dte.now()
            self.user_agent = ua
            self.cookies = json.dumps(dict(r.cookies))
            self.save()
            rebot_log.info("登陆成功cbd %s", self.telephone)
            return "OK"
        else:
            self.modify(is_active=False)
            rebot_log.error("登陆错误cbd %s, %s", self.telephone, str(ret))
        return "fail"

    @property
    def proxy_ip(self):
        rds = get_redis("default")
        ipstr = self.ip
        if ipstr and rds.sismember(RK_PROXY_IP_CBD, ipstr):
            return ipstr
        ipstr = rds.srandmember(RK_PROXY_IP_CBD)
        self.modify(ip=ipstr)
        return ipstr

    def http_get(self, url, **kwargs):
        try:
            r = requests.get(url,
                             proxies={"http": "http://%s" % self.proxy_ip},
                             timeout=10,
                             **kwargs)
        except Exception, e:
            self.modify(ip="")
            raise e
        return r

    def http_post(self, url, **kwargs):
        try:
            r = requests.post(url,
                              proxies={"http": "http://%s" % self.proxy_ip},
                              timeout=30,
                              **kwargs)
        except Exception, e:
            self.modify(ip="")
            raise e
        return r


class ChangtuWebRebot(Rebot):
    user_agent = db.StringField()
    cookies = db.StringField()
    ip = db.StringField()

    meta = {
        "indexes": ["telephone", "is_active", "is_locked"],
        "collection": "changtuweb_rebot",
    }

    crawl_source = SOURCE_CHANGTU
    is_for_lock = True

    @property
    def proxy_ip(self):
        return ""

    def on_add_doing_order(self, order):
        self.modify(is_locked=True)

    def on_remove_doing_order(self, order):
        self.modify(is_locked=False)

    def login(self):
        ua = random.choice(BROWSER_USER_AGENT)
        self.last_login_time = dte.now()
        self.user_agent = ua
        self.is_active = True
        self.cookies = "{}"
        self.save()
        rebot_log.info("创建成功 %s", self.telephone)
        return "OK"

    def test_login_status(self):
        check_url = "http://www.changtu.com/trade/order/userInfo.htm"
        headers = {"User-Agent": self.user_agent}
        cookies = json.loads(self.cookies)
        resp = requests.get(check_url, headers=headers, cookies=cookies)
        c = resp.content
        c = c[c.index("(") + 1: c.rindex(")")]
        res = json.loads(c)
        if res["loginFlag"] == "true":
            return 1
        return 0


class JsdlkyWebRebot(Rebot):
    user_agent = db.StringField()
    cookies = db.StringField(default="{}")
    ip = db.StringField()

    meta = {
        "indexes": ["telephone", "is_active", "is_locked"],
        "collection": "jsdlkyweb_rebot",
    }
    crawl_source = SOURCE_JSDLKY
    is_for_lock = True

    @property
    def proxy_ip(self):
        return ""

    def login(self, headers=None, cookies={}, valid_code=""):
        index_url = "http://www.jslw.gov.cn/"
        valid_code = valid_code or "1234"
        if not headers:
            ua = random.choice(BROWSER_USER_AGENT)
            headers = {"User-Agent": ua}
        if not cookies:
            r = self.http_get(index_url, headers=headers)
            cookies = dict(r.cookies)

        add_secret = lambda s: "".join(
            map(lambda b: str(hex(ord(b))).lstrip("0x"), s))
        params = {
            "returnurl":  "",
            "event": "login",
            "password1":  add_secret(self.password),
            "user_code1": add_secret(self.telephone),
            "user_code": self.telephone,
            "password": self.password,
            "rememberMe": "yes",
        }
        params.update(checkcode=valid_code)

        login_url = "http://www.jslw.gov.cn/login.do"
        headers["Content-Type"] = "application/x-www-form-urlencoded"
        r = self.http_post(login_url,
                           data=urllib.urlencode(params),
                           allow_redirects=False,
                           headers=headers, cookies=cookies)
        r_cookies = dict(r.cookies)
        cookies.update(r_cookies)
        if r.headers.get("location", "") and r_cookies["userId"]:
            self.last_login_time = dte.now()
            self.user_agent = headers["User-Agent"]
            self.is_active = True
            self.cookies = json.dumps(cookies)
            self.save()
            return "OK"
        else:
            return "fail"

    def test_login_status(self):
        user_url = "http://www.jslw.gov.cn/registerUser.do"
        headers = {"User-Agent": self.user_agent}
        r = self.http_get(user_url, headers=headers,
                          cookies=json.loads(self.cookies))
        sel = etree.HTML(r.content)
        try:
            username = sel.xpath("//li[@class='user']/text()")[0]
            assert username == self.telephone
            return 1
        except:
            self.modify(cookies="{}")
            return 0


class BabaWebRebot(Rebot):
    user_agent = db.StringField()
    cookies = db.StringField()

    meta = {
        "indexes": ["telephone", "is_active", "is_locked"],
        "collection": "babaweb_rebot",
    }
    crawl_source = SOURCE_BABA
    is_for_lock = True

    def clear_riders(self):
        return
        is_login = self.test_login_status()
        if not is_login:
            return
        rider_url = "http://www.bababus.com/passenger/list.htm"
        del_url = "http://www.bababus.com/passenger/del.htm"
        headers = {"User-Agent": self.user_agent}
        post_headers = {
            "User-Agent": self.user_agent,
            "Content-Type": "application/x-www-form-urlencoded",
        }
        cookies = json.loads(self.cookies)
        for i in range(3):  # 删前3页
            r = requests.get(rider_url, headers=headers, cookies=cookies)
            sel = etree.HTML(r.content)
            id_lst = sel.xpath("//input[@name='c_passengerId']/@value")
            if not id_lst:
                break
            lst = [
                "passengerIds=%s" % ",".join(id_lst),
            ]
            lst.extend(map(lambda s: "c_passengerId=%s" % s, id_lst))
            data = "&".join(lst)
            requests.post(del_url, data=data,
                          headers=post_headers, cookies=cookies)

    def on_add_doing_order(self, order):
        rebot_log.info("[baba] %s locked", self.telephone)
        self.modify(is_locked=True)

    def on_remove_doing_order(self, order):
        rebot_log.info("[baba] %s unlocked", self.telephone)
        self.modify(is_locked=False)

    def login(self):
        ua = random.choice(BROWSER_USER_AGENT)
        self.last_login_time = dte.now()
        self.user_agent = ua
        self.is_active = True
        self.cookies = "{}"
        self.save()
        rebot_log.info("创建成功 %s", self.telephone)
        return "OK"

    def check_login_by_resp(self, resp):
        result = urlparse.urlparse(resp.url)
        if "login" in result.path:
            return 0
        return 1

    def test_login_status(self):
        undone_order_url = "http://www.bababus.com/order/list.htm?billStatus=0&currentLeft=11"
        headers = {"User-Agent": self.user_agent}
        cookies = json.loads(self.cookies)
        resp = requests.get(undone_order_url, headers=headers, cookies=cookies)
        return self.check_login_by_resp(resp)


class JskyWebRebot(Rebot):
    user_agent = db.StringField()
    cookies = db.StringField()

    meta = {
        "indexes": ["telephone", "is_active", "is_locked"],
        "collection": "jskyweb_rebot",
    }
    crawl_source = SOURCE_JSKY

    def login(self):
        ua = random.choice(BROWSER_USER_AGENT)
        login_url = "http://www.jskylwsp.com/Account/LoginIn"
        data = {
            "UserName": self.telephone,
            "Password": self.password,
        }
        header = {
            "User-Agent": ua,
        }
        r = requests.post(login_url, data=data, headers=header)
        ret = r.json()
        if ret["response"]["header"]["rspCode"] == "0000":
            self.is_active = True
            self.last_login_time = dte.now()
            self.user_agent = ua
            self.cookies = json.dumps(dict(r.cookies))
            self.save()
            rebot_log.info("登陆成功webjsky %s", self.telephone)
            return "OK"
        else:
            rebot_log.error("登陆错误webjsky %s, %s", self.telephone, str(ret))
        return "fail"


class JskyAppRebot(Rebot):
    user_agent = db.StringField()
    member_id = db.StringField()
    authorize_code = db.StringField()

    meta = {
        "indexes": ["telephone", "is_active", "is_locked"],
        "collection": "jskyapp_rebot",
    }
    crawl_source = SOURCE_JSKY
    is_for_lock = True

    def post_data_templ(self, service_name, body):
        stime = str(int(time.time() * 1000))
        tmpl = {
            "body": body,
            "clientInfo": {
                "clientIp": "192.168.111.106",
                "deviceId": "898fd52b362f6a9c",
                "extend": "4^4.4.4,5^MI 4W,6^-1",
                "macAddress": "14:f6:5a:b9:d1:4a",
                "networkType": "wifi",
                "platId": "20",
                "pushInfo": "",
                "refId": "82037323",
                "versionNumber": "1.0.0",
                "versionType": "1"
            },
            "header": {
                "accountID": "d4a45219-f2f2-4a2a-ab7b-007ee848629d",
                "digitalSign": md5(stime),
                "reqTime": stime,
                "serviceName": service_name,
                "version": "20150526020002"
            }
        }
        return tmpl

    def http_header(self, ua=""):
        return {
            "Charset": "UTF-8",
            "Content-Type": "application/json; charset=UTF-8",
            "reqdata": "c9e70e4f9d58df70b3f416d067895b13",
            "User-Agent": ua or self.user_agent,
        }

    def login(self):
        ua = random.choice(MOBILE_USER_AGENG)
        log_url = "http://api.jskylwsp.cn/ticket-interface/rest/member/login"
        pwd_info = SOURCE_INFO[SOURCE_JSKY]["pwd_encode"]
        body = {
            "mobileNo": self.telephone,
            "password": pwd_info[self.password],
        }
        data = self.post_data_templ("login", body)
        header = self.http_header(ua=ua)
        r = requests.post(log_url, data=json.dumps(data), headers=header)
        ret = r.json()
        if ret["header"]["rspCode"] == "0000":
            self.is_active = True
            self.last_login_time = dte.now()
            self.user_agent = ua
            self.member_id = ret["body"]["memberId"]
            self.authorize_code = ret["body"]["authorizeCode"]
            self.save()
            rebot_log.info("登陆成功 jsky %s", self.telephone)
            return "OK"
        else:
            rebot_log.error("登陆错误jsky %s, %s", self.telephone, str(ret))
        return "fail"


class CTripRebot(Rebot):
    user_agent = db.StringField()
    head = db.DictField()

    meta = {
        "indexes": ["telephone", "is_active", "is_locked"],
        "collection": "ctrip_rebot",
    }
    crawl_source = SOURCE_CTRIP
    is_for_lock = True

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
        # driver = webdriver.PhantomJS(desired_capabilities=dcap)
        driver = webdriver.Firefox()
        driver.set_window_size(1120, 550)
        login = "https://accounts.ctrip.com/H5Login/Index"
        driver.get(login)
        wait = WebDriverWait(driver, 10)
        username = wait.until(
            EC.presence_of_element_located((By.ID, "username")))
        username.send_keys(self.telephone)
        password = wait.until(
            EC.presence_of_element_located((By.ID, "password")))
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
                return "OK"
        driver.quit()
        rebot_log.info("%s 登陆失败" % self.telephone)
        return "fail"

    def http_post(self, url, data):
        request = urllib2.Request(url)
        request.add_header('User-Agent', self.user_agent)
        request.add_header('Content-type', "application/json; charset=UTF-8")
        qstr = json.dumps(data)
        response = urllib2.urlopen(request, qstr, timeout=30)
        ret = json.loads(response.read())
        return ret


class CqkyWebRebot(Rebot):
    user_agent = db.StringField()
    cookies = db.StringField(default="{}")
    ip = db.StringField(default="")

    meta = {
        "indexes": ["telephone", "is_active", "is_locked", "ip"],
        "collection": "cqkyweb_rebot",
    }
    crawl_source = SOURCE_CQKY
    is_for_lock = True

    @property
    def proxy_ip(self):
        rds = get_redis("default")
        ipstr = self.ip
        if ipstr and rds.sismember(RK_PROXY_IP_CQKY, ipstr):
            return ipstr
        ipstr = rds.srandmember(RK_PROXY_IP_CQKY)
        self.modify(ip=ipstr)
        return ipstr

    @classmethod
    def get_one(cls, order=None):
        today = dte.now().strftime("%Y-%m-%d")
        all_accounts = set(cls.objects.filter(
            is_active=True, is_locked=False).distinct("telephone"))
        droped = set()
        for d in Order.objects.filter(status=14,
                                      crawl_source='cqky',
                                      create_date_time__gte=today) \
                .aggregate({
                    "$group": {
                        "_id": {"phone": "$source_account"},
                        "count": {"$sum": "$ticket_amount"}}
                }):
            cnt = d["count"]
            phone = d["_id"]["phone"]
            if cnt >= 7:
                droped.add(phone)
        tele = random.choice(list(all_accounts - droped))
        return cls.objects.get(telephone=tele)

    def on_add_doing_order(self, order):
        rebot_log.info("[cqky] %s locked", self.telephone)
        self.modify(is_locked=True)

    def on_remove_doing_order(self, order):
        rebot_log.info("[cqky] %s unlocked", self.telephone)
        self.modify(is_locked=False)

    def login(self, valid_code="", headers={}, cookies={}):
        vcode_flag = False
        if not valid_code:
            login_form = "http://www.96096kp.com/CusLogin.aspx"
            valid_url = "http://www.96096kp.com/ValidateCode.aspx"
            headers = {"User-Agent": random.choice(BROWSER_USER_AGENT)}
            r = self.http_get(login_form, headers=headers, cookies=cookies)
            cookies.update(dict(r.cookies))
            r = self.http_get(valid_url, headers=headers, cookies=cookies)
            valid_code = vcode_cqky(r.content)
            vcode_flag = True

        if valid_code:
            headers = {
                "User-Agent": headers.get("User-Agent", "") or self.user_agent,
                "Referer": "http://www.96096kp.com/CusLogin.aspx",
                "Origin": "http://www.96096kp.com",
                "Content-Type": "application/x-www-form-urlencoded; charset=UTF-8",
            }
            params = {
                "loginID": self.telephone,
                "loginPwd": self.password,
                "getInfo": 1,
                "loginValid": valid_code,
                "cmd": "Login",
            }
            login_url = "http://www.96096kp.com/UserData/UserCmd.aspx"
            r = self.http_post(login_url, data=urllib.urlencode(
                params), headers=headers, cookies=cookies)
            res = json.loads(trans_js_str(r.content))
            success = res.get("success", True)
            if success:     # 登陆成功
                username = res["Code"]
                if username != self.telephone:  # cookie串了
                    self.modify(cookies="{}")
                    return "fail"
                cookies.update(dict(r.cookies))
                self.modify(cookies=json.dumps(cookies), is_active=True)
                rebot_log.info("[cqky]登陆成功, %s vcode_flag:%s",
                               self.telephone, vcode_flag)
                return "OK"
            else:
                msg = res["msg"]
                rebot_log.info("[cqky]%s %s vcode_flag:%s",
                               self.telephone, msg, vcode_flag)
                if u"用户名或密码错误" in msg:
                    return "invalid_pwd"
                elif u"请正确输入验证码" in msg or u"验证码已过期" in msg:
                    return "invalid_code"
                return msg
        else:
            ua = random.choice(BROWSER_USER_AGENT)
            self.last_login_time = dte.now()
            self.user_agent = ua
            self.is_active = True
            self.cookies = "{}"
            self.save()
            return "fail"

    def test_login_status(self):
        login_url = "http://www.96096kp.com/UserData/UserCmd.aspx"
        headers = {
            "User-Agent": self.user_agent,
            "Referer": "http://www.96096kp.com/TicketMain.aspx",
            "Origin": "http://www.96096kp.com",
            "Content-Type": "application/x-www-form-urlencoded; charset=UTF-8",
        }
        cookies = json.loads(self.cookies)
        today = dte.now().strftime("%Y-%m-%d")
        params = {
            "beginDate": today,
            "endDate": today,
            "isCheck": "false",
            "Code": "",
            "cmd": "GetMobileList",
        }
        r = self.http_post(login_url, data=urllib.urlencode(
            params), headers=headers, cookies=cookies)
        lst = re.findall(r'success:"(\w+)"', r.content)
        succ = lst and lst[0] or ""
        if succ == "true":
            return 1
        return 0


class TCAppRebot(Rebot):
    member_id = db.StringField()
    user_id = db.StringField()

    meta = {
        "indexes": ["telephone", "is_active", "is_locked"],
        "collection": "tcapp_rebot",
    }
    crawl_source = SOURCE_TC
    is_for_lock = True

    def http_post(self, url, service_name, data):
        stime = str(int(time.time() * 1000))
        account_id = "c26b007f-c89e-431a-b8cc-493becbdd8a2"
        version = "20111128102912"
        s = "AccountID=%s&ReqTime=%s&ServiceName=%s&Version=%s" % (
            account_id, stime, service_name, version)
        digital_sign = md5(s + "8874d8a8b8b391fbbd1a25bda6ecda11")
        params = OrderedDict()
        params["request"] = OrderedDict()
        s = """{"request":{"body":{"clientInfo":{"clientIp":"192.168.111.104","deviceId":"898fd52b362f6a9c","extend":"4^4.4.4,5^MI 4W,6^-1","mac":"14:f6:5a:b9:d1:4a","manufacturer":"Xiaomi","networkType":"wifi","pushInfo":"d//igwEhgBGCI2TG6lWqlK1bASX03rDfA3JbL/g8WWZAjh0HL+Xl4O6Gnz/Md0IMtK5xaQLx2gx0lrKjigw0va5kMl4fwRtaflQwB/JWvEE=","refId":"16359978","tag":"|^^0^1^91^0^|","versionNumber":"8.0.5","versionType":"android"},"isUserLogin":"1","password":"X8OreO1LsvFYfESF/pau4chTlTsG2LB9bSaTxbq2GYcesBmrBKgsb7bFy9F/K5AC","loginName":"17051322878"},"header":{"accountID":"c26b007f-c89e-431a-b8cc-493becbdd8a2","digitalSign":"d9f62ee2d12b65eca96e5f14f13ff733","reqTime":"1458673470243","serviceName":"Loginv2","version":"20111128102912"}}}"""
        params = {
            "request": {
                "body": {
                    "clientInfo": {
                        "clientIp": "192.168.111.104",
                        "deviceId": "898fd52b362f6a9c",
                        "extend": "4^4.4.4,5^MI 4W,6^-1",
                        "mac": "14:f6:5a:b9:d1:4a",
                        "manufacturer": "Xiaomi",
                        "networkType": "wifi",
                        "pushInfo": "d//igwEhgBGCI2TG6lWqlK1bASX03rDfA3JbL/g8WWZAjh0HL+Xl4O6Gnz/Md0IMtK5xaQLx2gx0lrKjigw0va5kMl4fwRtaflQwB/JWvEE=",
                        "refId": "16359978",
                        "tag": "|^^0^1^91^0^|",
                        "versionNumber": "8.0.5",
                        "versionType": "android",
                    },
                },
                "header": {
                    "accountID": account_id,
                    "digitalSign": digital_sign,
                    "reqTime": stime,
                    "serviceName": service_name,
                    "version": version,
                }
            }
        }
        params["request"]["body"].update(data)
        body = json.dumps(params)
        req_data = md5(body + "4957CA66-37C3-46CB-B26D-E3D9DCB51535")
        headers = {
            "secver": 5,
            "reqdata": req_data,
            "alisign": "ab88e5c9-0266-4526-872c-7a9e15ce78fd",
            "sxx": "f28c70d32017edb57cfe4d6fc1a9d5b2",
            "Content-Type": "application/json",
            "User-Agent": "okhttp/2.5.0",
        }
        r = requests.post(url, data=body, headers=headers)
        return r

    def login(self):
        if self.test_login_status():
            rebot_log.info("已登陆 tcapp %s", self.telephone)
            return "OK"
        log_url = "http://tcmobileapi.17usoft.com/member/MembershipHandler.ashx"
        data = OrderedDict({
            "isUserLogin": "1",
            "password": SOURCE_INFO[SOURCE_TC]["pwd_encode_app"][self.password],
            "loginName": self.telephone
        })
        data["isUserLogin"] = "1"
        data["password"] = SOURCE_INFO[SOURCE_TC][
            "pwd_encode_app"][self.password]
        data["loginName"] = self.telephone
        r = self.http_post(log_url, "Loginv2", data)
        res = r.json()["response"]
        if res["header"]["rspCode"] == "0000":
            self.is_active = True
            self.last_login_time = dte.now()
            self.member_id = res["body"]["memberId"]
            self.user_id = res["body"]["externalMemberId"]
            self.save()
            rebot_log.info("登陆成功 tcapp %s", self.telephone)
            return "OK"
        else:
            self.update(is_active=False)
            rebot_log.info("登陆错误 tcapp %s, %s", self.telephone, str(res))
        return "fail"

    def test_login_status(self):
        user_url = "http://tcmobileapi.17usoft.com/member/membershiphandler.ashx"
        data = {
            "memberId": self.member_id,
            "loginName": self.telephone,
        }
        r = self.http_post(user_url, "QueryMemberInfo", data)
        res = r.json()["response"]
        if res["header"]["rspCode"] == "0000":
            return 1
        return 0


class TCWebRebot(Rebot):
    user_agent = db.StringField()
    cookies = db.StringField(default="{}")
    user_id = db.StringField()
    ip = db.StringField(default="")

    meta = {
        "indexes": ["telephone", "is_active", "is_locked"],
        "collection": "tc_rebot",
    }
    crawl_source = SOURCE_TC
    is_for_lock = False

    def login(self, headers=None, cookies={}, valid_code=""):
        login_url = "https://passport.ly.com/Member/MemberLoginAjax.aspx"
        pwd_info = SOURCE_INFO[self.crawl_source]["pwd_encode"]
        data = {
            "remember": 30,
            "name": self.telephone,
            "pass": pwd_info[self.password],
            "action": "login",
            "validCode": valid_code,
        }
        if not headers:
            headers = {
                "User-Agent": random.choice(BROWSER_USER_AGENT),
            }
        headers.update({"Content-Type": "application/x-www-form-urlencoded"})
        r = self.http_post(login_url,
                           data=urllib.urlencode(data),
                           headers=headers,
                           cookies=cookies,
                           verify=False)
        cookies.update(dict(r.cookies))
        ret = r.json()
        if int(ret["state"]) == 100:    # 登录成功
            self.last_login_time = dte.now()
            self.user_agent = headers["User-Agent"]
            self.cookies = json.dumps(cookies)
            for s in cookies["us"].split("&"):
                k, v = s.split("=")
                if k == "userid":
                    self.user_id = v
                    break
            self.save()
            rebot_log.info("登陆成功 %s %s", self.crawl_source, self.telephone)
            return "OK"
        else:
            self.modify(is_active=True)
            rebot_log.error("登陆失败 %s %s, %s", self.crawl_source,
                            self.telephone, str(ret))
            return "fail"

    def check_login_by_resp(self, resp):
        result = urlparse.urlparse(resp.url)
        if result.netloc == u"passport.ly.com":
            return 0
        return 1

    def test_login_status(self):
        user_url = "http://member.ly.com/Member/MemberInfomation.aspx"
        headers = {
            "User-Agent": self.user_agent or random.choice(BROWSER_USER_AGENT)}
        cookies = json.loads(self.cookies)
        resp = self.http_get(user_url, headers=headers,
                             cookies=cookies, verify=False)
        return self.check_login_by_resp(resp)

    @property
    def proxy_ip(self):
        return ""
        rds = get_redis("default")
        ipstr = self.ip
        if ipstr and rds.sismember(RK_PROXY_IP_TC, ipstr):
            return ipstr
        ipstr = rds.srandmember(RK_PROXY_IP_TC)
        self.modify(ip=ipstr)
        return ipstr


class GzqcpWebRebot(Rebot):
    user_agent = db.StringField()
    cookies = db.StringField()

    meta = {
        "indexes": ["telephone", "is_active", "is_locked"],
        "collection": "gzqcpweb_rebot",
    }
    crawl_source = SOURCE_GZQCP

    def test_login_status(self):
        try:
            user_url = "http://www.gzsqcp.com//com/yxd/pris/grzx/grzl/detailPersonalData.action"
            headers = {"User-Agent": self.user_agent}
            cookies = json.loads(self.cookies)
            data = {"memberId": "2"}
            res = requests.post(user_url, data=data,
                                headers=headers, cookies=cookies)
            res = res.json()
            if res.get('akfAjaxResult', '') == '0' and res['values']['member']:
                return 1
            else:
                return 0
        except:
            return 0

    @classmethod
    def login_all(cls):
        """预设账号"""
        rebot_log.info(">>>> start to init gzqcp web:")
        valid_cnt = 0
        has_checked = {}
        accounts = SOURCE_INFO[SOURCE_GZQCP]["accounts"]
        for bot in cls.objects:
            has_checked[bot.telephone] = 1
            if bot.telephone not in accounts:
                bot.modify(is_active=False)
                continue
            pwd = accounts[bot.telephone][0]
            bot.modify(password=pwd)

        for tele, (pwd, _) in accounts.items():
            if tele in has_checked:
                continue
            bot = cls(is_active=True,
                      is_locked=False,
                      telephone=tele,
                      user_agent=random.choice(BROWSER_USER_AGENT),
                      password=pwd,)
            bot.save()
            valid_cnt += 1
        rebot_log.info(">>>> end init gzqcp web  success %d", valid_cnt)


class GzqcpAppRebot(Rebot):
    user_agent = db.StringField()
    cookies = db.StringField()

    meta = {
        "indexes": ["telephone", "is_active", "is_locked"],
        "collection": "gzqcpapp_rebot",
    }
    crawl_source = SOURCE_GZQCP
    is_for_lock = True

    def http_header(self, ua=""):
        return {
            "Charset": "UTF-8",
            "Content-Type": "application/x-www-form-urlencoded; charset=UTF-8",
            "User-Agent": ua or self.user_agent,
        }

    @classmethod
    def get_one(cls, order=None):
        now = dte.now()
        start = now.strftime("%Y-%m-%d") + ' 00:00:00'
        start = dte.strptime(start, '%Y-%m-%d %H:%M:%S')
        all_accounts = SOURCE_INFO[SOURCE_GZQCP]["accounts"].keys()
        used = Order.objects.filter(crawl_source=SOURCE_GZQCP,
                                    status=STATUS_ISSUE_SUCC,
                                    create_date_time__gt=start) \
            .item_frequencies("source_account")
        accounts_list = filter(lambda k: used.get(k, 0) < 20, all_accounts)
        for i in range(100):
            choose = random.choice(accounts_list)
            rebot = cls.objects.get(telephone=choose)
            if rebot.is_active:
                return rebot

    def on_add_doing_order(self, order):
        rebot_log.info("[gzqcp] %s locked", self.telephone)
        self.modify(is_locked=True)

    def on_remove_doing_order(self, order):
        rebot_log.info("[gzqcp] %s unlocked", self.telephone)
        self.modify(is_locked=False)

    def login(self):
        ua = random.choice(MOBILE_USER_AGENG)
        header = {
            "User-Agent": ua,
        }
        data = {
            "username": self.telephone,
            "password": self.password
        }
        log_url = "http://www.gzsqcp.com/com/yxd/pris/openapi/personLogin.action"
        r = requests.post(log_url, data=data, headers=header)
        ret = r.json()
        if int(ret["akfAjaxResult"]) == 0 and int(ret["values"]['result']["code"]) == 1:
            self.last_login_time = dte.now()
            self.user_agent = ua
            self.cookies = json.dumps(dict(r.cookies))
            self.is_active = True
            self.save()
            rebot_log.info("登陆成功gzqcp %s", self.telephone)
            return "OK"
        else:
            rebot_log.error("登陆错误gzqcp %s, %s", self.telephone, str(ret))
            return "fail"

    def test_login_status(self):
        try:
            user_url = "http://www.gzsqcp.com//com/yxd/pris/openapi/detailPersonalData.action"
            headers = {"User-Agent": self.user_agent}
            cookies = json.loads(self.cookies)
            data = {}
            res = requests.post(user_url, data=data,
                                headers=headers, cookies=cookies)
            res = res.json()
            if res.get('akfAjaxResult', '') == '0' and res['values']['member']:
                return 1
            else:
                return 0
        except:
            return 0


class KuaibaWapRebot(Rebot):
    user_agent = db.StringField()
    cookies = db.StringField()
    user_id = db.StringField()

    meta = {
        "indexes": ["telephone", "is_active", "is_locked"],
        "collection": "kuaibawap_rebot",
    }
    crawl_source = SOURCE_KUAIBA
    is_for_lock = True

    def http_header(self, ua=""):
        return {
            "Charset": "UTF-8",
            "Content-Type": "application/x-www-form-urlencoded; charset=UTF-8",
            "User-Agent": ua or self.user_agent,
        }

    def on_add_doing_order(self, order):
        rebot_log.info("[kuaiba] %s locked", self.telephone)
        self.modify(is_locked=True)

    def on_remove_doing_order(self, order):
        rebot_log.info("[kuaiba] %s unlocked", self.telephone)
        self.modify(is_locked=False)

    def login(self):
        ua = random.choice(MOBILE_USER_AGENG)
        header = {
            "User-Agent": ua,
        }
        pwd_info = SOURCE_INFO[SOURCE_KUAIBA]["pwd_encode"]
        params = {
            "account": self.telephone,
            "password": pwd_info[self.password]
        }
        url = "http://m.daba.cn/gwapi/kbUser/userLogin.json?c=h5&sr=&sc=&ver=1.5.0&env=0&st="
        login_url = "%s&%s" % (url, urllib.urlencode(params))
        r = requests.get(login_url, headers=header)
        ret = r.json()
        if int(ret["code"]) == 0 and ret["msg"] == '成功':
            self.last_login_time = dte.now()
            self.user_agent = ua
            self.cookies = json.dumps(dict(r.cookies))
            self.is_active = True
            self.save()
            rebot_log.info("登陆成功 kuaiba %s", self.telephone)
            self.test_login_status()
            return "OK"
        else:
            rebot_log.error("登陆错误 kuaiba %s, %s", self.telephone, str(ret))
            return "fail"

    def test_login_status(self):
        try:
            user_url = "http://m.daba.cn/gwapi/passenger/queryPassengers.json?c=h5&sr=6963&sc=729&ver=1.5.0&env=0&st=1456996592487"
            headers = {"User-Agent": self.user_agent}
            cookies = json.loads(self.cookies)
            res = requests.get(user_url, headers=headers, cookies=cookies)
            res = res.json()
            if res['code'] == 0:
                if res.get('data', []) and not self.user_id:
                    user_id = res.get('data', [])[0]['userid']
                    self.user_id = user_id
                    self.save()
                return 1
            else:
                return 0
        except:
            return 0

    def clear_riders(self):
        try:
            query_url = "http://m.daba.cn/gwapi/passenger/queryPassengers.json?c=h5&sr=2985&sc=162&ver=1.5.0&env=0&st=1456998910554"
            if not self.test_login_status():
                self.login()
                self.reload()
            headers = self.http_header()
            r = requests.get(query_url, headers=headers,
                             cookies=json.loads(self.cookies))
            ret = r.json()
            if ret['code'] == 0:
                for i in ret['data']:
                    cyuserid = i['cyuserid']
                    del_url = "http://m.daba.cn/gwapi/passenger/deletePassenger.json?c=h5&sr=5975&sc=111&ver=1.5.0&env=0&st=1458898047519&passengerId=%s" % cyuserid
                    r = requests.get(del_url, headers=headers,
                                     cookies=json.loads(self.cookies))
        except:
            pass


class BjkyWebRebot(Rebot):
    user_agent = db.StringField()
    cookies = db.StringField(default="{}")
    ip = db.StringField(default="")

    meta = {
        "indexes": ["telephone", "is_active", "is_locked"],
        "collection": "bjkyweb_rebot",
    }
    crawl_source = SOURCE_BJKY
    is_for_lock = True

    def http_header(self, ua=""):
        return {
            "Charset": "UTF-8",
            "Content-Type": "application/x-www-form-urlencoded; charset=UTF-8",
            "User-Agent": ua or self.user_agent,
        }

    @property
    def proxy_ip(self):
        return ''
#         rds = get_redis("default")
#         ipstr = self.ip
#         key = RK_PROXY_IP_BJKY
#         if ipstr and rds.sismember(key, ipstr):
#             return ipstr
#         ipstr = rds.srandmember(key)
#         self.modify(ip=ipstr)
#         return ipstr

    @classmethod
    def get_one(cls, order=None):
        today = dte.now().strftime("%Y-%m-%d")
        all_accounts = set(cls.objects.filter(
            is_active=True, is_locked=False).distinct("telephone"))
        droped = set()
        for d in Order.objects.filter(status=14,
                                      crawl_source=SOURCE_BJKY,
                                      lock_datetime__gt=today) \
                .aggregate({
                    "$group": {
                        "_id": {"phone": "$source_account"},
                        "count": {"$sum": "$ticket_amount"}}
                }):
            cnt = d["count"]
            phone = d["_id"]["phone"]
            if cnt + int(order.ticket_amount) > 3:
                droped.add(phone)
        tele = random.choice(list(all_accounts - droped))
        return cls.objects.get(telephone=tele)

    @classmethod
    def login_all(cls):
        """登陆所有预设账号"""
        rebot_log.info(">>>> start to init bjky:")
        valid_cnt = 0
        has_checked = {}
        ua = random.choice(BROWSER_USER_AGENT)
        accounts = SOURCE_INFO[SOURCE_BJKY]["accounts"]
        for bot in cls.objects:
            has_checked[bot.telephone] = 1
            if bot.telephone not in accounts:
                bot.modify(is_active=False)
                continue
            pwd, _ = accounts[bot.telephone]
            bot.modify(password=pwd)

#             if bot.login() == "OK":
#                 rebot_log.info("%s 登陆成功" % bot.telephone)
#                 valid_cnt += 1
        for tele, (pwd, _) in accounts.items():
            if tele in has_checked:
                continue
            bot = cls(is_active=True,
                      is_locked=False,
                      telephone=tele,
                      password=pwd,
                      user_agent=ua
                      )
            bot.save()
#             if bot.login() == "OK":
#                 rebot_log.info("%s 登陆成功" % bot.telephone)
            valid_cnt += 1
        rebot_log.info(">>>> end init bjky success %d", valid_cnt)

    def test_login_status(self):
        try:
            url = "http://e2go.com.cn/TicketOrder/Notic"
    #         cookie ="Hm_lvt_0b26ef32b58e6ad386a355fa169e6f06=1456970104,1457072900,1457316719,1457403102; ASP.NET_SessionId=uuppwd3q4j3qo5vwcka2v04y; Hm_lpvt_0b26ef32b58e6ad386a355fa169e6f06=1457415243"
    #         headers={"cookie":cookie}
    #         cookies = {"Hm_lvt_0b26ef32b58e6ad386a355fa169e6f06": "1456970104,1457072900,1457316719,1457403102",
    #                                        "ASP.NET_SessionId": "uuppwd3q4j3qo5vwcka2v04y",
    #                                        "Hm_lpvt_0b26ef32b58e6ad386a355fa169e6f06": "1457415243"}
            headers = {"User-Agent": self.user_agent}
            cookies = json.loads(self.cookies or '{}')
            res = self.http_get(url, headers=headers, cookies=cookies)
            result = urlparse.urlparse(res.url)
            if result.path == '/Home/Login':
                return 0
            else:
                content = res.content
                if not isinstance(content, unicode):
                    content = content.decode('utf-8')
                sel = etree.HTML(content)
                telephone = sel.xpath('//*[@id="logoutContainer"]/text()')
                if telephone:
                    telephone = telephone[0].replace(
                        '\r\n', '').replace('\t', '').replace(' ', '')
                if self.telephone == telephone:
                    return 1
                else:
                    self.modify(cookies='{}')
                    self.modify(ip="")
                    self.reload()
                    return 0
        except:
            self.modify(cookies='{}')
            self.modify(ip="")
            self.reload()
            return 0


class LnkyWapRebot(Rebot):
    user_agent = db.StringField()
    cookies = db.StringField()
    ip = db.StringField(default="")

    meta = {
        "indexes": ["telephone", "is_active", "is_locked"],
        "collection": "lnkywap_rebot",
    }
    crawl_source = SOURCE_LNKY
    is_for_lock = True

    @property
    def proxy_ip(self):
        return ''
#         rds = get_redis("default")
#         ipstr = self.ip
#         key = RK_PROXY_IP_LNKY
#         if ipstr and rds.sismember(key, ipstr):
#             return ipstr
#         ipstr = rds.srandmember(key)
#         self.modify(ip=ipstr)
#         return ipstr

    def http_header(self, ua=""):
        return {
            "Charset": "UTF-8",
            "Content-Type": "application/x-www-form-urlencoded; charset=UTF-8",
            "User-Agent": self.user_agent or ua,
        }

    def on_add_doing_order(self, order):
        rebot_log.info("[lnky] %s locked", self.telephone)
        self.modify(is_locked=True)

    def on_remove_doing_order(self, order):
        rebot_log.info("[lnky] %s unlocked", self.telephone)
        self.modify(is_locked=False)

    def login(self):
        ua = random.choice(MOBILE_USER_AGENG)
        headers = self.http_header(ua)
        pwd_info = SOURCE_INFO[SOURCE_LNKY]["pwd_encode"]
        data = {
            "userInfo.account": self.telephone,
            "userInfo.password": pwd_info[self.password]
        }
        login_url = "http://www.jt306.cn/wap/login/ajaxLogin.do"
        r = self.http_post(login_url, data=data, headers=headers)
        ret = r.json()
        if ret["returnCode"] == '0000':
            self.last_login_time = dte.now()
            self.user_agent = self.user_agent or ua
            self.cookies = json.dumps(dict(r.cookies))
            self.is_active = True
            self.save()
            rebot_log.info("登陆成功 lnky %s", self.telephone)
            return "OK"
        else:
            rebot_log.error("登陆错误 lnky %s, %s", self.telephone, str(ret))
            return "fail"

    def test_login_status(self):
        try:
            user_url = "http://www.jt306.cn/wap/userCenter/personalInformation.do"
            headers = self.http_header()
            cookies = json.loads(self.cookies)
            res = self.http_get(user_url, headers=headers, cookies=cookies)
            result = urlparse.urlparse(res.url)
            if 'login/loginPage.do' in result.path:
                return 0
            else:
                return 1
        except:
            return 0


class LnkyWebRebot(Rebot):
    user_agent = db.StringField()
    cookies = db.StringField()
    ip = db.StringField(default="")
    user_id = db.StringField()

    meta = {
        "indexes": ["telephone", "is_active", "is_locked"],
        "collection": "lnkyweb_rebot",
    }
    crawl_source = SOURCE_LNKY
    is_for_lock = True

    @property
    def proxy_ip(self):
        return ''
#         rds = get_redis("default")
#         ipstr = self.ip
#         key = RK_PROXY_IP_LNKY
#         if ipstr and rds.sismember(key, ipstr):
#             return ipstr
#         ipstr = rds.srandmember(key)
#         self.modify(ip=ipstr)
#         return ipstr

    def http_header(self, ua=""):
        return {
            "Charset": "UTF-8",
            "Content-Type": "application/x-www-form-urlencoded; charset=UTF-8",
            "User-Agent": self.user_agent or ua,
        }

    def on_add_doing_order(self, order):
        rebot_log.info("[lnky] %s locked", self.telephone)
        self.modify(is_locked=True)

    def on_remove_doing_order(self, order):
        rebot_log.info("[lnky] %s unlocked", self.telephone)
        self.modify(is_locked=False)

    def login(self):
        ua = random.choice(BROWSER_USER_AGENT)
        headers = self.http_header(ua)
        pwd_info = SOURCE_INFO[SOURCE_LNKY]["pwd_encode"]
        data = {
              "account": self.telephone,
              "password": pwd_info[self.password]
              }
        login_url = 'http://www.jt306.cn/ticket/uc/login.action'
        cookies = {}
        r = self.http_post(url=login_url, data=data, headers=headers)
        content = r.content
        if not isinstance(content, unicode):
            content = content.decode('utf-8')
        cookies.update(dict(r.cookies))
        sel = etree.HTML(content)
        login_error = sel.xpath('//form[@id="ucJumpForm"]/p[@class="ui-state-error"]/text()')
        if not login_error:
            matchObj = re.findall('top.infoLogin\((.*)\);', content)
            user_info = matchObj[0].split(',')
            username = user_info[0][1:-1]
            user_id = user_info[1][1:-1]
            self.last_login_time = dte.now()
            self.user_agent = self.user_agent or ua
            self.cookies = json.dumps(cookies)
            self.is_active = True
            self.user_id = user_id
            self.save()
            rebot_log.info("登陆成功 lnky %s,username:%s", self.telephone,username)
            return "OK"
        else:
            rebot_log.error("登陆错误 lnky %s, %s", self.telephone, str(login_error[0]))
            return "fail"

    def test_login_status(self):
        try:
            user_url = "http://www.jt306.cn/ticket/uc/goUpdate.action?userId=%s"%self.user_id
            headers = self.http_header()
            cookies = json.loads(self.cookies)
            data = {}
            res = self.http_post(user_url, data=data, headers=headers, cookies=cookies)
            content = res.content
            if self.telephone in content:
                return 1
            else:
                return 0
        except:
            return 0


class E8sAppRebot(Rebot):
    user_agent = db.StringField(
        default="Apache-HttpClient/UNAVAILABLE (java 1.4)")
    user_id = db.StringField()
    ip = db.StringField(default="")

    meta = {
        "indexes": ["telephone", "is_active", "is_locked"],
        "collection": "e8sapp_rebot",
    }
    crawl_source = SOURCE_E8S
    is_for_lock = True

    def on_add_doing_order(self, order):
        self.modify(is_locked=True)

    def on_remove_doing_order(self, order):
        self.modify(is_locked=False)

    @property
    def proxy_ip(self):
        rds = get_redis("default")
        ipstr = self.ip
        if ipstr and rds.sismember(RK_PROXY_IP_E8S, ipstr):
            return ipstr
        ipstr = rds.srandmember(RK_PROXY_IP_E8S)
        self.modify(ip=ipstr)
        return ipstr

    def http_header(self, ua=""):
        return {
            "Charset": "UTF-8",
            "Content-Type": "application/x-www-form-urlencoded; charset=UTF-8",
            "User-Agent": self.user_agent or ua,
        }

    def login(self):
        headers = self.http_header()
        data = {
            "password": self.password,
            "userName": self.telephone
        }
        url = "http://m.e8s.com.cn/bwfpublicservice/login.action"
        r = self.http_post(url, data=data, headers=headers)
        ret = r.json()
        if not ret["detail"]:
            # 登陆失败
            self.is_active = False
            self.last_login_time = dte.now()
            self.save()
            return ret.get("msg", "fail")
        else:
            # 登陆成功
            self.user_id = str(ret["detail"]['USER_ID'])
            self.is_active = True
            self.last_login_time = dte.now()
            self.save()
            return "OK"


class HebkyAppRebot(Rebot):
    user_agent = db.StringField()
    cookies = db.StringField()
    ip = db.StringField(default="")

    meta = {
        "indexes": ["telephone", "is_active", "is_locked"],
        "collection": "hebkyapp_rebot",
    }
    crawl_source = SOURCE_HEBKY
    is_for_lock = True

    def on_add_doing_order(self, order):
        rebot_log.info("[hebky] %s locked", self.telephone)
        self.modify(is_locked=True)

    def on_remove_doing_order(self, order):
        rebot_log.info("[hebky] %s unlocked", self.telephone)
        self.modify(is_locked=False)

    @property
    def proxy_ip(self):
        return ''
#         rds = get_redis("default")
#         ipstr = self.ip
#         key = RK_PROXY_IP_HEBKY
#         if ipstr and rds.sismember(key, ipstr):
#             return ipstr
#         ipstr = rds.srandmember(key)
#         self.modify(ip=ipstr)
#         return ipstr

    def http_header(self, ua=""):
        return {
            "Charset": "UTF-8",
            "Content-Type": "application/x-www-form-urlencoded; charset=UTF-8",
            "User-Agent": ua or self.user_agent,
        }

    @classmethod
    def get_one(cls, order=None):
        today = dte.now().strftime("%Y-%m-%d")
        all_accounts = set(cls.objects.filter(
            is_active=True, is_locked=False).distinct("telephone"))
        droped = set()
        for d in Order.objects.filter(status=14,
                                      crawl_source=SOURCE_HEBKY,
                                      lock_datetime__gt=today) \
                .aggregate({
                    "$group": {
                        "_id": {"phone": "$source_account"},
                        "count": {"$sum": "$ticket_amount"}}
                }):
            cnt = d["count"]
            phone = d["_id"]["phone"]
            if cnt + int(order.ticket_amount) > 10:
                droped.add(phone)
        tele = random.choice(list(all_accounts - droped))
        return cls.objects.get(telephone=tele)

    def login(self):
        ua = random.choice(MOBILE_USER_AGENG)
        header = {
            "User-Agent": ua,
        }
        data = {
            "username": self.telephone,
            "password": self.password
        }
        log_url = "http://60.2.147.28/com/yxd/pris/openapi/personLogin.action"
        r = self.http_post(log_url, data=data, headers=header)
        ret = r.json()
        if int(ret["akfAjaxResult"]) == 0 and int(ret["values"]['result']["code"]) == 1:
            self.last_login_time = dte.now()
            self.user_agent = ua
            self.cookies = json.dumps(dict(r.cookies))
            self.is_active = True
            self.save()
            rebot_log.info("登陆成功 hebky %s", self.telephone)
            return "OK"
        else:
            rebot_log.error("登陆错误 hebky %s, %s", self.telephone, str(ret))
            return "fail"

    def test_login_status(self):
        try:
            user_url = "http://60.2.147.28/com/yxd/pris/grzx/grzl/detailPersonalData.action"
            headers = {"User-Agent": self.user_agent}
            cookies = json.loads(self.cookies)
            data = {"memberId": "2"}
            res = self.http_post(user_url, data=data,
                                 headers=headers, cookies=cookies)
            res = res.json()
            if res.get('akfAjaxResult', '') == '0' and res['values']['member']:
                userName = res['values']['member']['userName']
                if userName == self.telephone:
                    return 1
                else:
                    self.modify(cookies='')
                    return 0
        except:
            return 0


class HebkyWebRebot(Rebot):
    user_agent = db.StringField()
    cookies = db.StringField()

    meta = {
        "indexes": ["telephone", "is_active", "is_locked"],
        "collection": "hebkyweb_rebot",
    }
    crawl_source = SOURCE_HEBKY

    @property
    def proxy_ip(self):
        return ''

    def test_login_status(self):
        try:
            user_url = "http://www.hb96505.com//com/yxd/pris/grzx/grzl/detailPersonalData.action"
            headers = {"User-Agent": self.user_agent}
            cookies = json.loads(self.cookies)
            data = {}
            res = self.http_post(user_url, data=data,
                                 headers=headers, cookies=cookies)
            res = res.json()
            if res.get('akfAjaxResult', '') == '0' and res['values']['member']:
                userName = res['values']['member']['userName']
                if userName == self.telephone:
                    return 1
                else:
                    self.modify(cookies='')
                    return 0
            else:
                return 0
        except:
            return 0

    @classmethod
    def login_all(cls):
        """预设账号"""
        rebot_log.info(">>>> start to init hebky web:")
        valid_cnt = 0
        has_checked = {}
        accounts = SOURCE_INFO[SOURCE_HEBKY]["accounts"]
        for bot in cls.objects:
            has_checked[bot.telephone] = 1
            if bot.telephone not in accounts:
                bot.modify(is_active=False)
                continue
            pwd = accounts[bot.telephone][0]
            bot.modify(password=pwd)

        for tele, (pwd, _) in accounts.items():
            if tele in has_checked:
                continue
            bot = cls(is_active=True,
                      is_locked=False,
                      telephone=tele,
                      user_agent=random.choice(BROWSER_USER_AGENT),
                      password=pwd,)
            bot.save()
            valid_cnt += 1
        rebot_log.info(">>>> end init hebky web  success %d", valid_cnt)


class NmghyWebRebot(Rebot):
    user_agent = db.StringField()
    cookies = db.StringField()
    ip = db.StringField(default="")

    meta = {
        "indexes": ["telephone", "is_active", "is_locked"],
        "collection": "nmghyweb_rebot",
    }
    crawl_source = SOURCE_NMGHY
    is_for_lock = True

    def on_add_doing_order(self, order):
        rebot_log.info("[nmghy] %s locked", self.telephone)
        self.modify(is_locked=True)

    def on_remove_doing_order(self, order):
        rebot_log.info("[nmghy] %s unlocked", self.telephone)
        self.modify(is_locked=False)

    @property
    def proxy_ip(self):
        return ''

    def http_header(self, ua=""):
        return {
            "Charset": "UTF-8",
            "Content-Type": "application/x-www-form-urlencoded;",
            "User-Agent": self.user_agent or ua,
            'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
            'Accept-Language': 'zh-CN,zh;q=0.8,en-US;q=0.5,en;q=0.3',
            "Connection": "keep-alive"
        }

    @classmethod
    def get_one(cls, order=None):
        today = dte.now().strftime("%Y-%m-%d")
        all_accounts = set(cls.objects.filter(
            is_active=True, is_locked=False).distinct("telephone"))
        droped = set()
        for d in Order.objects.filter(status=14,
                                      crawl_source=SOURCE_NMGHY,
                                      lock_datetime__gt=today) \
                .aggregate({
                    "$group": {
                        "_id": {"phone": "$source_account"},
                        "count": {"$sum": "$ticket_amount"}}
                }):
            cnt = d["count"]
            phone = d["_id"]["phone"]
            if cnt + int(order.ticket_amount) > 5:
                droped.add(phone)
        tele = random.choice(list(all_accounts - droped))
        return cls.objects.get(telephone=tele)

    def login(self):
        ua = random.choice(BROWSER_USER_AGENT)
        headers = self.http_header(ua)
        data = {
            "username": self.telephone,
            "password": self.password,
            "ispost": "1"
        }
        login_url = "http://www.nmghyjt.com/index.php/login/index"
        r = requests.post(login_url, data=data, headers=headers)
        content = r.content
        if not isinstance(content, unicode):
            content = content.decode('utf-8')
        sel = etree.HTML(content)
        telephone = sel.xpath(
            '//div[@class="login-info"]/span/a[@id="login_user"]/text()')
        if telephone:
            if telephone[0] == self.telephone:
                self.last_login_time = dte.now()
                self.user_agent = ua
                self.cookies = json.dumps(dict(r.cookies))
                self.is_active = True
                self.save()
                rebot_log.info("登陆成功 nmghy %s", self.telephone)
                self.test_login_status()
                return "OK"
            else:
                rebot_log.error("登陆错误 nmghy %s, %s",
                                self.telephone, str(telephone))
                return "fail"
        else:
            rebot_log.error("登陆错误 nmghy %s, %s",
                            self.telephone, str(telephone))
            return "fail"

    def test_login_status(self):
        try:
            url = "http://www.nmghyjt.com/index.php/login/getuserstatus"
            headers = self.http_header()
            cookies = json.loads(self.cookies)
            data = {}
            res = self.http_post(
                url, data=data, headers=headers, cookies=cookies)
            content = res.content
            if not isinstance(content, unicode):
                content = content.decode('utf-8')
            sel = etree.HTML(content)
            telephone = sel.xpath('//a[@id="login_user"]/text()')
            if telephone:
                if telephone[0] == self.telephone:
                    return 1
                else:
                    self.modify(cookies='')
                    return 0
            else:
                return 0
        except:
            return 0


class Bus365AppRebot(Rebot):
    user_agent = db.StringField(
        default="Apache-HttpClient/UNAVAILABLE (java 1.4)")
    user_id = db.StringField(default="")
    client_token = db.StringField(default="")
    deviceid = db.StringField(default="")
    clientinfo = db.StringField(default="")
    ip = db.StringField(default="")

    meta = {
        "indexes": ["telephone", "is_active", "is_locked"],
        "collection": "bus365app_rebot",
    }
    crawl_source = SOURCE_BUS365
    is_for_lock = True

    def on_add_doing_order(self, order):
        rebot_log.info("[bus365] %s locked", self.telephone)
        self.modify(is_locked=True)

    def on_remove_doing_order(self, order):
        rebot_log.info("[bus365] %s unlocked", self.telephone)
        self.modify(is_locked=False)

    @property
    def proxy_ip(self):
        rds = get_redis("default")
        ipstr = self.ip
        if ipstr and rds.sismember(RK_PROXY_IP_BUS365, ipstr):
            return ipstr
        ipstr = rds.srandmember(RK_PROXY_IP_BUS365)
        self.modify(ip=ipstr)
        return ipstr

    def http_header(self, ua=""):
        return {
            "Charset": "UTF-8",
            "Content-Type": "application/x-www-form-urlencoded;",
            "User-Agent": self.user_agent or ua,
            'Accept-Language': 'zh-CN,zh;q=0.8,en-US;q=0.5,en;q=0.3',
            "Connection": "keep-alive",
            "accept": "application/json,",
        }

    @classmethod
    def get_one(cls, order=None):
        today = dte.now().strftime("%Y-%m-%d")
        all_accounts = set(cls.objects.filter(
            is_active=True, is_locked=False).distinct("telephone"))
        droped = set()
        for d in Order.objects.filter(status=14,
                                      crawl_source=SOURCE_BUS365,
                                      lock_datetime__gt=today) \
                .aggregate({
                    "$group": {
                        "_id": {"phone": "$source_account"},
                        "count": {"$sum": "$ticket_amount"}}
                }):
            cnt = d["count"]
            phone = d["_id"]["phone"]
            if cnt + int(order.ticket_amount) > 25:
                droped.add(phone)
        tele = random.choice(list(all_accounts - droped))
        return cls.objects.get(telephone=tele)

    def get_random_deviceid(self):
        maclist = []
        for i in range(1, 7):
            RANDSTR = "".join(random.sample("0123456789abcdef", 2))
            maclist.append(RANDSTR)
        mac = ":".join(maclist)
        return mac

    def login(self):
        headers = self.http_header()
        pwd_info = SOURCE_INFO[SOURCE_BUS365]["pwd_encode"]
        clientinfo = {"browsername": "", "browserversion": "",
                      "clienttype": "1", "computerinfo": "", "osinfo": "android 4.4.2"}
        deviceid = self.deviceid or self.get_random_deviceid()
        data = {
            "user.username": self.telephone,
            "clientinfo": json.dumps(clientinfo),
            "user.password": pwd_info[self.password],
            "token": '{"clienttoken":"","clienttype":"android"}',
            "clienttype": "android",
            "usertoken": '',
            "deviceid": deviceid,
        }
        login_url = "http://www.bus365.com/user/login"
        r = self.http_post(login_url, data=data, headers=headers)
        try:
            ret = r.json()
        except:
            self.modify(ip='')
            r = self.http_post(login_url, data=data, headers=headers)
            ret = r.json()
        if ret:
            if ret['username'] == self.telephone:
                self.last_login_time = dte.now()
                self.is_active = True
                self.user_id = ret['id']
                self.clientinfo = json.dumps(clientinfo)
                self.deviceid = deviceid
                self.client_token = ret['clienttoken']
                self.save()
                rebot_log.info("登陆成功 bus365 %s", self.telephone)
                return "OK"
            else:
                rebot_log.error("登陆错误 bus365 %s, %s", self.telephone, str(ret))
                return "fail"
        else:
            rebot_log.error("登陆错误 bus365 %s, %s", self.telephone, str(ret))
            return "fail"

    def recrawl_shiftid(self, line):
        """
        重新获取线路ID
        """
        init_params = {
            "token": '{"clienttoken":"","clienttype":"android"}',
            "clienttype": "android",
            "usertoken": ''
        }
        params = {
            "departdate": line.drv_date,
            "departcityid": line.extra_info['start_info']['id'],
            "reachstationname": line.d_city_name
        }
        params.update(init_params)
        url = "http://%s/schedule/searchscheduler2/0" % line.extra_info[
            'start_info']['netname']
        line_url = "%s?%s" % (url, urllib.urlencode(params))
        request = urllib2.Request(line_url)
        request.add_header(
            'User-Agent', "Apache-HttpClient/UNAVAILABLE (java 1.4)")
        request.add_header('Content-type', "application/x-www-form-urlencoded")
        request.add_header('accept', "application/json,")
        request.add_header('clienttype', "android")
        request.add_header('clienttoken', "")

        response = urllib2.urlopen(request, timeout=30)
        res = json.loads(response.read())
        for d in res['schedules']:
            if int(d['iscansell']) == 1:
                item = {}
                drv_datetime = dte.strptime("%s %s" % (
                    line.drv_date, d['departtime'][0:-3]), "%Y-%m-%d %H:%M")
                line_id_args = {
                    "s_city_name": line.s_city_name,
                    "d_city_name": line.d_city_name,
                    "s_sta_name": d["busshortname"],
                    "d_sta_name": d["stationname"],
                    "bus_num": d["schedulecode"],
                    "crawl_source": line.crawl_source,
                    "drv_datetime": drv_datetime,
                }
                line_id = md5(
                    "%(s_city_name)s-%(d_city_name)s-%(drv_datetime)s-%(s_sta_name)s-%(d_sta_name)s-%(crawl_source)s" % line_id_args)
                item['line_id'] = line_id
                item['shift_id'] = d['id']
                item["refresh_datetime"] = dte.now()
                item["full_price"] = float(d["fullprice"])
                item["left_tickets"] = int(d["residualnumber"])
                try:
                    line_obj = Line.objects.get(line_id=line_id)
                    line_obj.modify(**item)
                except Line.DoesNotExist:
                    continue


class Bus365WebRebot(Rebot):
    user_agent = db.StringField()
    cookies = db.StringField()

    meta = {
        "indexes": ["telephone", "is_active", "is_locked"],
        "collection": "bus365web_rebot",
    }
    crawl_source = SOURCE_BUS365

    @property
    def proxy_ip(self):
        return ''

    def test_login_status(self):
        try:
            user_url = "http://www.bus365.com/userinfo0"
            headers = {
                "User-Agent": self.user_agent,
                "Content-Type": "application/x-www-form-urlencoded"
            }
            cookies = json.loads(self.cookies)
            res = self.http_get(user_url, headers=headers, cookies=cookies)
            content = res.content
            if not isinstance(content, unicode):
                content = content.decode('utf-8')
            sel = etree.HTML(content)
            telephone = sel.xpath('//form[@name="user.username"]/text()')
            if telephone:
                if telephone[0] == self.telephone:
                    return 1
                else:
                    self.modify(cookies='')
                    return 0
            else:
                return 0
        except:
            return 0

    @classmethod
    def login_all(cls):
        """预设账号"""
        rebot_log.info(">>>> start to init bus365 web:")
        valid_cnt = 0
        has_checked = {}
        accounts = SOURCE_INFO[SOURCE_BUS365]["accounts"]
        for bot in cls.objects:
            has_checked[bot.telephone] = 1
            if bot.telephone not in accounts:
                bot.modify(is_active=False)
                continue
            pwd = accounts[bot.telephone][0]
            bot.modify(password=pwd)

        for tele, (pwd, _) in accounts.items():
            if tele in has_checked:
                continue
            bot = cls(is_active=True,
                      is_locked=False,
                      telephone=tele,
                      user_agent=random.choice(BROWSER_USER_AGENT),
                      password=pwd,)
            bot.save()
            valid_cnt += 1
        rebot_log.info(">>>> end init bus365 web  success %d", valid_cnt)


class XinTuYunWebRebot(Rebot):
    user_agent = db.StringField()
    cookies = db.StringField()
    ip = db.StringField(default="{}")

    meta = {
        "indexes": ["telephone", "is_active", "is_locked"],
        "collection": "xintuyunweb_rebot",
    }
    crawl_source = SOURCE_XINTUYUN
    is_for_lock = True

    @property
    def proxy_ip(self):
        return ''

    def on_add_doing_order(self, order):
        rebot_log.info("[xintuyun] %s locked", self.telephone)
        self.modify(is_locked=True)

    def on_remove_doing_order(self, order):
        rebot_log.info("[xintuyun] %s unlocked", self.telephone)
        self.modify(is_locked=False)

    def http_header(self, ua=""):
        return {
            "Charset": "UTF-8",
            "Content-Type": "application/x-www-form-urlencoded; charset=UTF-8",
            "User-Agent": self.user_agent or ua,
        }

    @classmethod
    def get_one(cls, order=None):
        today = dte.now().strftime("%Y-%m-%d")
        all_accounts = set(cls.objects.filter(is_active=True, is_locked=False).distinct("telephone"))
        droped = set()
        if order:
            for d in Order.objects.filter(status=14,
                                          crawl_source=SOURCE_XINTUYUN,
                                          lock_datetime__gt=today) \
                                  .aggregate({
                                      "$group":{
                                          "_id": {"phone": "$source_account"},
                                          "count": {"$sum": "$ticket_amount"}}
                                  }):
                cnt = d["count"]
                phone = d["_id"]["phone"]
                if cnt + int(order.ticket_amount) > 20:
                    droped.add(phone)
        tele = random.choice(list(all_accounts-droped))
        return cls.objects.get(telephone=tele)

    def test_login_status(self):
        url = "http://www.xintuyun.cn/user.shtml"
        headers = self.http_header()
        cookies = json.loads(self.cookies)
        res = self.http_post(url, cookies=cookies, headers=headers)
        content = res.content
        if not isinstance(content, unicode):
            content = content.decode('utf8')
        check_str = self.telephone.replace(self.telephone[3:7], '****')
        if check_str in content:
            return 1
        return 0

    def login(self, valid_code="", token='', headers={}, cookies={}):
        """
        返回OK表示登陆成功
        """
        vcode_flag = False
        valid_code = "".join(random.sample("0123456789abcdefghijklmnopqrstuvwxzy",4)),
#         if not valid_code:
#             login_form_url = "http://www.xintuyun.cn/login.shtml?%s"%time.time()
#             headers = {"User-Agent": random.choice(BROWSER_USER_AGENT)}
#             r = self.http_get(login_form_url, headers=headers, cookies=cookies)
#             sel = etree.HTML(r.content)
#             cookies.update(dict(r.cookies))
#             code_url = sel.xpath("//img[@id='validateImg']/@src")[0]
#             code_url = 'http://www.xintuyun.cn'+code_url
#             token = sel.xpath("//input[@id='csrfmiddlewaretoken1']/@value")[0]
#             r = self.http_get(code_url, headers=headers, cookies=cookies)
#             cookies.update(dict(r.cookies))
#             valid_code = vcode_xintuyun(r.content)
#             vcode_flag = True

        if valid_code:
            headers = {
                "User-Agent": headers.get("User-Agent", "") or self.user_agent,
                "Content-Type": "application/x-www-form-urlencoded; charset=UTF-8",
            }
            data = {
                "loginType": 0,
                "backUrl": '',
                "mobile": self.telephone,
                "password": self.password,
                "validateCode": valid_code
            }
            login_url = "http://www.xintuyun.cn/doLogin/ajax"
            r = self.http_post(login_url, data=data, headers=headers, cookies=cookies)
            res = r.json()
            if res["flag"] == '0':     # 登陆成功
                mobile = res["customer"]['mobile']
                if mobile != self.telephone:  # cookie串了
                    self.modify(cookies="{}")
                    return "fail"
                cookies.update(dict(r.cookies))
                self.modify(cookies=json.dumps(cookies), is_active=True)
                rebot_log.info("[xintuyun]登陆成功, %s vcode_flag:%s", self.telephone, vcode_flag)
                return "OK"
            else:
                msg = res["msg"]
                rebot_log.info("[xintuyun]%s %s vcode_flag:%s", self.telephone, msg, vcode_flag)
                if u"验证码不正确" in msg:
                    return "invalid_code"
                return msg
        else:
            ua = random.choice(BROWSER_USER_AGENT)
            self.last_login_time = dte.now()
            self.user_agent = ua
            self.is_active = True
            self.cookies = "{}"
            self.save()
        rebot_log.info("创建成功 %s", self.telephone)
        return "OK"

    def recrawl_shiftid(self, line):
        """
        重新获取线路ID
        """
        queryline_url = 'http://www.xintuyun.cn/getBusShift/ajax'
        start_city_id = line.s_sta_id
        start_city_name = line.s_city_name
        target_city_name = line.d_sta_name
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
            "sendTimes": '',
            "showRemainOnly": '',
            "sort": "1",
            "startId": start_city_id,
            'startName': start_city_name,
            'stationIds': '',
            'ttsId': ''
            }
        return self.recrawl_func(line, queryline_url, payload)

    def recrawl_func(self, line, queryline_url, payload, is_exist=False):
        res = requests.post(queryline_url, data=payload)
        trainListInfo = res.json()
        if trainListInfo and trainListInfo.get('msg', ''):
            nextPage = int(trainListInfo['nextPage'])
            pageNo = int(trainListInfo['pageNo'])
            content = trainListInfo['msg']
            if not isinstance(content, unicode):
                content = content.decode('utf8')
            sel = etree.HTML(content)
            trains = sel.xpath('//div[@class="trainList"]')
            for n in trains:
                d_str = n.xpath("@data-list")[0]
                shift_str = d_str[d_str.index("id=")+3:]
                left_str = d_str[d_str.index("leftSeatNum=")+12:]
                shiftid = shift_str[:shift_str.index(",")]
                leftSeatNum = left_str[:left_str.index(",")]
                item = {}
                time = n.xpath('ul/li[@class="time"]/p/strong/text()')
                item['drv_time'] = time[0]
                drv_datetime = dte.strptime(payload['sendDate']+' '+time[0], "%Y-%m-%d %H:%M")
                bus_num = ''
                bus_num = n.xpath('ul/li[@class="time"]/p[@class="carNum"]/text()')
                if bus_num:
                    bus_num = bus_num[0].replace('\r\n', '').replace(' ',  '')
                bus_num = bus_num.decode("utf-8").strip().rstrip(u"次")
                price = n.xpath('ul/li[@class="price"]/strong/text()')
                flag = 0
                buyInfo = n.xpath('ul/li[@class="buy"]/a[@class="btn"]/text()')
                if buyInfo:
                    flag = 1
                full_price = float(str(price[0]).split('￥')[-1])
                line_id_args = {
                    "s_city_name": line.s_city_name,
                    "d_city_name": line.d_city_name,
                    "bus_num": bus_num,
                    "crawl_source": line.crawl_source,
                    "drv_datetime": drv_datetime,
                }
                line_id = md5("%(s_city_name)s-%(d_city_name)s-%(drv_datetime)s-%(bus_num)s-%(crawl_source)s" % line_id_args)
                try:
                    obj = Line.objects.get(line_id=line_id)
                except Line.DoesNotExist:
                    continue
                info = {
                    "full_price": full_price,
                    "fee": 0,
                    "left_tickets": int(leftSeatNum),
                    "refresh_datetime": dte.now(),
                    "extra_info": {"flag": flag},
                    "shift_id": shiftid
                }
                if line_id == line.line_id:
                    is_exist = True
                obj.modify(**info)

            if nextPage > pageNo:
                url = 'http://www.xintuyun.cn/getBusShift/ajax'+'?pageNo=%s' % nextPage
#                 url = queryline_url.split('?')[0]+'?pageNo=%s'%nextPage
                is_exist = self.recrawl_func(line, url, payload, is_exist)
        return is_exist

    def clear_riders(self):
        url = "http://www.xintuyun.cn/people.shtml"
        headers = self.http_header()
        cookies = json.loads(self.cookies)
        try:
            response = self.http_post(url, cookies=cookies, headers=headers)
            sel = etree.HTML(response.content)
            people_list = sel.xpath('//div[@class="p-edu"]')
            for i in people_list:
                res = i.xpath('a[@class="del trans"]/@onclick')[0]
                userid = re.findall('del\(\'(.*)\'\);', res)[0]
                del_url = "http://www.xintuyun.cn/user/delPeople/ajax?id=%s"%userid
                response = self.http_get(del_url, cookies=cookies, headers=headers)
        except:
            pass


class Bus100Rebot(Rebot):
    is_encrypt = db.IntField(choices=(0, 1))
    user_agent = db.StringField()
    token = db.StringField()
    open_id = db.StringField()
    cookies = db.DictField()

    meta = {
        "indexes": ["telephone", "is_active", "is_locked"],
    }
    crawl_source = SOURCE_BUS100
    is_for_lock = True

    @classmethod
    def get_one(cls, order=None):
        now = dte.now()
        start = now.strftime("%Y-%m-%d") + ' 00:00:00'
        start = dte.strptime(start, '%Y-%m-%d %H:%M:%S')
        all_accounts = SOURCE_INFO[SOURCE_BUS100]["accounts"].keys()
        used = Order.objects.filter(crawl_source='bus100',
                                    status=STATUS_ISSUE_SUCC,
                                    create_date_time__gt=start) \
            .item_frequencies("source_account")
        accounts_list = filter(lambda k: used.get(k, 0) < 20, all_accounts)
        for i in range(100):
            choose = random.choice(accounts_list)
            rebot = cls.objects.get(telephone=choose)
            if rebot.is_active:
                return rebot

    def test_login_status(self):
        url = "http://www.84100.com/user.shtml"
        res = requests.post(url, cookies=self.cookies)
        res = res.content
        sel = etree.HTML(res)
        userinfo = sel.xpath(
            '//div[@class="c_content"]/div/ul/li[@class="myOrder"]')
        if not userinfo:
            return 0
        return 1

    @classmethod
    def get_random_rebot(cls):
        qs = cls.objects.all()
        if not qs:
            return None
        size = qs.count()
        rd = random.randint(0, size - 1)
        return qs[rd]

    @classmethod
    def get_random_active_rebot(cls):
        qs = cls.objects.filter(is_active=True)
        if not qs:
            return None
        size = qs.count()
        rd = random.randint(0, size - 1)
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
            rebot_log.error("%s %s login failed! %s", self.telephone,
                            self.password, ret.get("returnMsg", ""))
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
            bot = cls(is_active=True,
                      is_locked=False,
                      telephone=tele,
                      password=pwd,
                      open_id=openid)
            bot.save()
#             if bot.login() == "OK":
#                 rebot_log.info("%s 登陆成功" % bot.telephone)
            valid_cnt += 1
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
        queryline_url = 'http://www.84100.com/getBusShift/ajax'
        start_city_id = line.s_sta_id
        start_city_name = line.s_city_name
        target_city_name = line.d_sta_name
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
        if trainListInfo and trainListInfo.get('msg', ''):
            nextPage = int(trainListInfo['nextPage'])
            pageNo = int(trainListInfo['pageNo'])
            sel = etree.HTML(trainListInfo['msg'])
            trains = sel.xpath('//div[@class="trainList"]')
            for n in trains:
                d_str = n.xpath("@data-list")[0]
                d_str = d_str[d_str.index("id=") + 3:]
                shiftid = d_str[:d_str.index(",")]

                item = {}
                time = n.xpath('ul/li[@class="time"]/p/strong/text()')
                item['drv_time'] = time[0]
                drv_datetime = dte.strptime(
                    payload['sendDate'] + ' ' + time[0], "%Y-%m-%d %H:%M")
                banci = ''
                banci = n.xpath(
                    'ul/li[@class="time"]/p[@class="carNum"]/text()')
                if banci:
                    banci = banci[0].replace('\r\n', '').replace(' ',  '')
                else:
                    ord_banci = n.xpath(
                        'ul/li[@class="time"]/p[@class="banci"]/text()')
                    if ord_banci:
                        banci = ord_banci[0]
                banci = banci.decode("utf-8").strip().rstrip(u"次")
#                 price = n.xpath('ul/li[@class="price"]/strong/text()')
#                 item["full_price"] = float(str(price[0]).split('￥')[-1])
                buyInfo = n.xpath('ul/li[@class="buy"]')
                flag = 0
                for buy in buyInfo:
                    flag = buy.xpath('a[@class="btn"]/text()')  # 判断可以买票
                    if flag:
                        flag = 1
                    else:
                        flag = 0
                item['extra_info'] = {"flag": flag}
                item['bus_num'] = str(banci)
                item['shift_id'] = str(shiftid)
                item["refresh_datetime"] = dte.now()
                line_id = md5("%s-%s-%s-%s-%s" %
                              (payload['startName'], payload['endName'], drv_datetime, str(banci), 'bus100'))
                item['line_id'] = line_id
                try:
                    line_obj = Line.objects.get(line_id=line_id)
                    line_obj.modify(**item)
                except Line.DoesNotExist:
                    continue

            if nextPage > pageNo:
                url = 'http://84100.com/getBusShift/ajax' + '?pageNo=%s' % nextPage
#                 url = queryline_url.split('?')[0]+'?pageNo=%s'%nextPage
                self.recrawl_func(url, payload)

    def clear_riders(self):
        url = "http://84100.com/people.shtml"
        try:
            response = requests.post(url, cookies=self.cookies)
            sel = etree.HTML(response.content)
            people_list = sel.xpath('//div[@class="p-edu"]')
            for i in people_list:
                res = i.xpath('a[@class="del trans"]/@onclick')[0]
                userid = re.findall('del\(\'(.*)\'\);', res)[0]
                del_url = "http://84100.com/user/delPeople/ajax?id=%s" % userid
                response = requests.get(del_url, cookies=self.cookies)
        except:
            pass


if not "_rebot_class" in globals():
    _rebot_class = {}
    for name in Rebot._subclasses:
        if name == "Rebot":
            continue
        cls = globals()[name]
        source = cls.crawl_source
        if not source:
            continue
        if source not in _rebot_class:
            _rebot_class[source] = []
        _rebot_class[source].append(cls)


def get_rebot_class(source):
    print(source)
    return _rebot_class.get(source, [])
