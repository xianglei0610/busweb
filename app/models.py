# -*- coding:utf-8 -*-
import urllib2
import urllib
import random
import copy

from datetime import datetime
from flask import json, current_app

from app.constans import SCQCP_ACCOUNTS
from app.constans import SCQCP_DOMAIN, MOBILE_USER_AGENG
from app import db


class Starting(db.Document):
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

    @property
    def pre_sell_days(self):
        """
        预售期
        """
        if not self.is_pre_sell:
            return 0
        if self.province_name == "四川" and self.crawl_source == "scqcp":
            return 10
        return 0

    @property
    def open_time(self):
        return "07:00:00"

    @property
    def end_time(self):
        return "23:00:00"

    @property
    def advance_order_time(self):
        return 120  # 2hour


class Destination(db.Document):
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
    distance = db.StringField()
    vehicle_type = db.StringField()  # 车型
    seat_type = db.StringField()     # 座位类型
    bus_num = db.StringField()       # 车次/班次
    full_price = db.FloatField()
    half_price = db.FloatField()
    fee = db.FloatField()           # 手续费
    crawl_datetime = db.DateTimeField()   # 爬取的时间
    extra_info = db.DictField()           # 额外信息字段

    @property
    def can_order(self):
        return 1

class Order(db.Document):
    """
    一个订单只对应一条线路
    """
    # 订单信息
    order_no = db.StringField(unique=True)
    status = db.IntField()
    order_price = db.FloatField()  # 订单金额
    create_date_time = db.DateTimeField()

    # 车票信息
    line = db.ReferenceField(Line)
    seat_no_list = db.ListField()
    ticket_price = db.FloatField()
    ticket_amount = db.IntField()
    ticket_fee = db.FloatField()   # 手续费
    discount = db.FloatField(default=0)     # 优惠金额

    # 支付信息
    pay_no = db.StringField()      # 支付号
    pay_status = db.IntField()
    pay_channel = db.StringField()     # 支付方式
    pay_account = db.StringField()
    pay_datetime = db.DateTimeField()

    # 联系人信息
    contacter_phone = db.StringField()
    contacter_name = db.StringField()
    contacter_idcard = db.StringField()

    # 乘客信息
    riders = db.ListField()

    # 锁票信息: 源网站在锁票这步返回的数据
    lock_info = db.DictField()

    # 其他
    crawl_source = db.StringField()   # 源网站
    extra_info = db.DictField()       # 额外信息

    @classmethod
    def generate_order_no(cls):
        import time
        return str(time.time()*10000000)


class ScqcpOrder(db.Document):
    """
    scqcp.com下订单时的返回信息
    """
    expire_time = db.DateTimeField()
    code = db.StringField()
    ticket_code = db.StringField()
    pay_order_id = db.LongField()
    ticket_list = db.ListField()
    ticket_lines = db.DictField()
    ticket_ids = db.ListField()
    order_ids = db.ListField()
    ticket_price_list = db.ListField()
    ticket_type = db.ListField()
    web_order_id = db.ListField()
    seat_number_list = db.ListField()
    lock_data = db.StringField()


class ScqcpRebot(db.Document):
    """
    机器人: 对被爬网站用户的抽象
    """
    telephone = db.StringField(required=True, unique=True)
    password = db.StringField()
    is_encrypt = db.IntField(choices=(0, 1))
    user_agent = db.StringField()
    token = db.StringField()
    open_id = db.StringField()
    is_active = db.BooleanField(default=True)  # 是否已被删除
    last_login_time = db.DateTimeField(default=datetime.now)

    meta = {
        "indexes": ["telephone", ],
    }

    def relogin(self):
        """
        返回OK表示登陆成功
        """
        ua = random.choice(MOBILE_USER_AGENG)
        device = "android" if "android" in ua else "ios"

        # 获取token
        uri = "/api/v1/api_token/get_token_for_app?channel=dxcd&version_code=40&oper_system=%s" % device
        url = urllib2.urlparse.urljoin(SCQCP_DOMAIN, uri)
        request = urllib2.Request(url)
        request.add_header('User-Agent', ua)
        response = urllib2.urlopen(request, timeout=5)
        ret = json.loads(response.read())
        token = ret["token"]

        # 登陆
        uri = "/api/v1/user/login_phone"
        data = {
            "username": self.telephone,
            "password": self.password,
            "is_encrypt": self.is_encrypt,
        }
        ret = self.http_post(uri, data, user_agent=ua, token=token)
        if "open_id" not in ret:
            # 登陆失败
            current_app.logger.error("%s %s login failed! %s", self.telephone, self.password, ret.get("msg", ""))
            self.update(is_active=False)
            return ret.get("msg", "fail")
        open_id = ret["open_id"]

        self.update(is_active=True, last_login_time=datetime.now(), user_agent=ua, token=token, open_id=open_id)
        return "OK"

    @classmethod
    def check_upsert_all(cls):
        """登陆所有预设账号"""
        now = datetime.now()
        current_app.logger.info(">>>> start to login scqcp.com:")
        valid_cnt = 0
        has_checked = {}
        for bot in cls.objects:
            has_checked[bot.telephone] = 1
            if bot.telephone not in SCQCP_ACCOUNTS:
                bot.update(is_active=False)
                continue
            pwd, is_encrypt = SCQCP_ACCOUNTS[bot.telephone]
            bot.update(password=pwd, is_encrypt=is_encrypt)

            # 近5天之内登陆的先不管
            if bot.is_active and (bot.last_login_time-now).seconds < 5*24*3600:
                valid_cnt += 1
                continue

            if bot.relogin() == "OK":
                valid_cnt += 1

        for tele, (pwd, is_encrypt) in SCQCP_ACCOUNTS.items():
            if tele in has_checked:
                continue
            bot = cls(is_active=False,
                      telephone=tele,
                      password=pwd,
                      is_encrypt=is_encrypt)
            bot .save()
            if bot.relogin() == "OK":
                valid_cnt += 1
        current_app.logger.info(">>>> end login scqcp.com, success %d", valid_cnt)


    def add_rider(self, name, id_card, birthday):
        uri = "/scqcp/api/v2/ticket/add_rider"
        data = {
            "open_id": self.open_id,
            "rider_name": name,
            "id_type": 0,
            "id_number": id_card,
            "birthday": birthday,
        }
        ret = self.http_post(uri, data)
        if ret["status"] == 1:
            current_app.logger.info("[%s] add rider(%s,%s) success!", self.telephone, name, id_card)
        else:
            current_app.logger.error("[%s] add rider(%s,%s) fail! %s", self.telephone, name, id_card, ret.get("msg", ""))

    def http_post(self, uri, data, user_agent=None, token=None):
        url = urllib2.urlparse.urljoin(SCQCP_DOMAIN, uri)
        request = urllib2.Request(url)
        request.add_header('User-Agent', user_agent or self.user_agent)
        request.add_header('Authorization', token or self.token)
        request.add_header('Content-type', "application/json; charset=UTF-8")
        qstr = urllib.urlencode(data)
        response = urllib2.urlopen(request, qstr, timeout=5)
        ret = json.loads(response.read())
        return ret

    def order(self, line, riders, contacter):
        """
        下订单
        """
        uri = "/api/v1/telecom/lock"
        tickets = []
        for r in riders:
            lst = [r["id_number"], r["real_name"], contacter, "0", "0"]

        data = {
            "carry_sta_id": line["carry_sta_id"],
            "stop_name": line["stop_name"],
            "str_date": line["str_date"],
            "sign_id": line["sign_id"],
            "phone_num": contacter,
            "buy_ticket_info": "$".join(tickets),
            "open_id": self.open_id,
        }
        ret = self.http_post(uri, data)
        if ret["status"] == 1:
            current_app.logger.info("order succ! %s", str(ret))
            attrs = copy.copy(ret)
            del attrs["status"]
            del attrs["msg"]
            ScqcpOrder(**attrs).save()
            return ""
        current_app.logger.info("order fail! %s", ret["msg"])
        return ret["msg"]

    def request_lock_ticket(self, order):
        """
        请求锁票
        """
        uri = "/api/v1/telecom/lock"
        tickets = []
        for r in order.riders:
            lst = [r["idcard"], r["name"], r["telephone"], "0", "0"]
            tickets.append("|".join(lst))

        data = {
            "carry_sta_id": order.line.starting.station_id,
            "stop_name": order.line.destination.station_name,
            "str_date": u"%s %s" % (order.line.drv_date, order.line.drv_time),
            "sign_id": order.line.extra_info["sign_id"],
            "phone_num": order.contacter_phone,
            "buy_ticket_info": "$".join(tickets),
            "open_id": self.open_id,
        }
        print data
        ret = self.http_post(uri, data)
        if ret["status"] == 1:
            current_app.logger.info("order succ! %s", str(ret))
            order.update(status=STATUS_LOCK, lock_info=ret)
            return ""
        return ret["msg"]

    def test_order(self):
        """
        临时测试方法，后期将移到单元测试模块
        """
        line = dict(
            carry_sta_id="zjcz",
            stop_name="八一",
            str_date="2015-12-01 18:40",
            sign_id="273d96c5817743b5ada282ce63d152d0"
            )
        contacter = "15575101324"
        riders = [
            {
                "id_number": "431021199004165616",
                "real_name": "罗军平",
            },
        ]
        self.order(line, riders, contacter)

