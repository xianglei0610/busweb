# -*- coding:utf-8 -*-
import urllib2
import urllib
import random

from app.constants import *
from app.async_tasks import async_issued_callback
from datetime import datetime
from flask import json, current_app

from app.constants import SCQCP_ACCOUNTS
from app.constants import SCQCP_DOMAIN, MOBILE_USER_AGENG
from app import db


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

    def max_ticket_per_order(self):
        if self.crawl_source == "scqcp":
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
    fee = db.FloatField()                 # 手续费
    crawl_datetime = db.DateTimeField()   # 爬取的时间
    extra_info = db.DictField()           # 额外信息字段

    @property
    def can_order(self):
        if not self.extra_info.get('flag',''):
            return 0
        return 1


class Order(db.Document):
    """
    一个订单只对应一条线路
    """
    # 订单信息
    order_no = db.StringField(unique=True)
    out_order_no = db.StringField()
    raw_order_no = db.StringField()
    status = db.IntField()
    order_price = db.FloatField()  # 订单金额
    create_date_time = db.DateTimeField()

    # 车票信息
    line = db.ReferenceField(Line)

    seat_no_list = db.ListField(db.StringField(max_length=10))
    ticket_price = db.FloatField()
    ticket_amount = db.IntField()
    ticket_fee = db.FloatField()            # 单张车票手续费
    discount = db.FloatField(default=0)     # 单张车票优惠金额

    # 支付信息
    pay_no = db.StringField()      # 支付号
    pay_status = db.IntField()
    pay_channel = db.StringField()     # 支付方式
    pay_account = db.StringField()
    pay_datetime = db.DateTimeField()

    # 乘客和联系人信息
    # 包含字段: name, telephone, id_type,id_number,age_level
    contact_info = db.DictField()
    riders = db.ListField(db.StringField(max_length=50))

    # 锁票信息: 源网站在锁票这步返回的数据
    lock_info = db.DictField()

    # 取票信息
    pick_code_list = db.ListField()     # 取票密码
    pick_msg_list = db.ListField()      # 取票说明

    # 其他
    crawl_source = db.StringField()     # 源网站
    extra_info = db.DictField()         # 额外信息
    locked_return_url = db.URLField()   # 锁票成功回调
    issued_return_url = db.URLField()   # 出票成功回调

    # 下单时使用的源网站账号
    source_account = db.StringField()

    def refresh_status(self):
        """
        刷新订单状态
        """
        if self.crawl_source == "scqcp" and self.status in [STATUS_ISSUE_DOING, STATUS_LOCK]:
            rebot = ScqcpRebot.objects.get(telephone=self.source_account)
            if not rebot.is_active:
                return False
            tickets = rebot.request_order(self)
            code_list = []
            if tickets and tickets.values()[0]["state"] == "success":
                # 出票成功
                for tid in self.lock_info["ticket_ids"]:
                    code_list.append(tickets[tid]["code"])
                self.update(status=STATUS_SUCC, pick_code_list=code_list)
                async_issued_callback(order)
        return True

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
            list.append({
                "name": info["name"],
                "telephone": info["telephone"],
                "id_type": info.get("idtype", IDTYPE_IDCARD),
                "id_number": info.get("id_number", ""),
                "age_level": info.get('age_level', RIDER_ADULT),
            })
        return lst

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


    @property
    def pay_url(self):
        if self.crawl_source == "scqcp":
            if "pay_order_id" not in self.lock_info:
                return ""
            url = "http://www.scqcp.com/ticketOrder/redirectOrder.html?pay_order_id=%s"
            return url % self.lock_info["pay_order_id"]
        return ""



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
            #if bot.is_active and (bot.last_login_time-now).seconds < 5*24*3600:
            #    valid_cnt += 1
            #    continue

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

    def http_post(self, uri, data, user_agent=None, token=None):
        url = urllib2.urlparse.urljoin(SCQCP_DOMAIN, uri)
        request = urllib2.Request(url)
        request.add_header('User-Agent', user_agent or self.user_agent)
        request.add_header('Authorization', token or self.token)
        request.add_header('Content-type', "application/json; charset=UTF-8")
        qstr = urllib.urlencode(data)
        response = urllib2.urlopen(request, qstr, timeout=10)
        ret = json.loads(response.read())
        return ret

    def request_lock_ticket(self, line, riders, contacter):
        """
        请求锁票
        """
        uri = "/api/v1/telecom/lock"
        tickets = []
        for r in riders:
            lst = [r["id_number"], r["real_name"], contacter, "0", "0"]
            tickets.append("|".join(lst))

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
        return ret

    def request_order(order):
        uri = "/api/v1/ticket_lines/query_order"
        ret = self.http_post(uri, {})
        ticket_ids = order.lock_info["ticket_ids"]
        amount = len(ticket_ids)
        data = {}
        for d in ret["ticket_list"]:
            if d["ticket_id"] in ticket_ids:
                data[d["ticket_id"]] = d
            if len(data) >= amount:
                break
        return data

    def test_order(self):
        """
        临时测试方法，后期将移到单元测试模块
        """
        line = dict(
            carry_sta_id="zjcz",
            stop_name="八一",
            str_date="2015-11-30 18:40",
            sign_id="cb31ec0dd90f4518892d82ce63d152d0"
            )
        contacter = "15575101324"
        riders = [
            {
                "id_number": "431021199004165616",
                "real_name": "罗军平",
            },
        ]
        self.request_lock_ticket(line, riders, contacter)
