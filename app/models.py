# -*- coding:utf-8 -*-
import random
import requests
import urllib
import urllib2
import re

from app.constants import *
from datetime import datetime
from flask import json, current_app
from lxml import etree
from contextlib import contextmanager
from app.constants import *
from app import db
from tasks import issued_callback
from app.utils import md5


class AdminUser(db.Document):
    """
    后台管理员/客服
    """
    username = db.StringField(max_length=30)
    password = db.StringField(max_length=50)
    create_datetime = db.DateTimeField(default=datetime.now)
    is_switch = db.IntField()
    is_kefu = db.IntField()

    meta = {
        "indexes": [
            "username",
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

    @property
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

    def refresh(self):
        """
        刷新
        """
        if self.crawl_source == SOURCE_SCQCP:
            params = dict(
                carry_sta_id=self.starting.station_id,
                stop_name=self.extra_info["stop_name_short"],
                drv_date="%s %s" % (self.drv_date, self.drv_time),
                sign_id=self.extra_info["sign_id"],
            )
            ua = random.choice(MOBILE_USER_AGENG)
            ret = ScqcpRebot.get_one().http_post("/scqcp/api/v2/ticket/query_plan_info", params, user_agent=ua)
            now = datetime.now()
            if ret["status"] == 1:
                if ret["plan_info"]:
                    raw = ret["plan_info"][0]
                    self.modify(full_price=raw["full_price"],
                                fee=raw["service_price"],
                                left_tickets=raw["amount"],
                                update_datetime=now)
                else:  # 线路信息没查到
                    self.modify(left_tickets=0, update_datetime=now)
            else:
                self.modify(left_tickets=0, update_datetime=now)
        elif self.crawl_source == SOURCE_BUS100:
            rebot = Bus100Rebot.objects.first()
            ret = rebot.recrawl_shiftid(self)
            line = Line.objects.get(line_id=self.line_id)
            url = 'http://www.84100.com/getTrainInfo/ajax'
            payload = {
                "shiftId": line.bus_num,
                "startId": line.starting.station_id,
                "startName": line.starting.station_name,
                "ttsId": ''
                     }
            try:
                trainInfo = requests.post(url, data=payload)
                trainInfo = trainInfo.json()
                left_tickets = 0
                if str(trainInfo['flag']) == '0':
                    sel = etree.HTML(trainInfo['msg'])
                    left_tickets = sel.xpath('//div[@class="ticketPrice"]/ul/li/strong[@id="leftSeatNum"]/text()')
                    if left_tickets:
                        left_tickets = int(left_tickets[0])
            except:
                left_tickets = 0
            now = datetime.now()
            self.modify(left_tickets=left_tickets, update_datetime=now)


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
    pay_url = db.StringField()      # 支付链接
    pay_no = db.StringField()      # 支付交易号
    pay_status = db.IntField()
    pay_channel = db.StringField()     # 支付方式
    pay_account = db.StringField()
    pay_datetime = db.DateTimeField()

    # 乘客和联系人信息
    # 包含字段: name, telephone, id_type,id_number,age_level
    contact_info = db.DictField()
    riders = db.ListField(db.DictField())

    # 锁票信息: 源网站在锁票这步返回的数据
    lock_info = db.DictField()

    # 取票信息
    pick_code_list = db.ListField(db.StringField(max_length=30))     # 取票密码
    pick_msg_list = db.ListField(db.StringField(max_length=50))      # 取票说明, len(pick_code_list)必须等于len(pick_msg_list)

    # 其他
    crawl_source = db.StringField()     # 源网站
    extra_info = db.DictField()         # 额外信息
    locked_return_url = db.URLField()   # 锁票成功回调
    issued_return_url = db.URLField()   # 出票成功回调

    # 下单时使用的源网站账号
    source_account = db.StringField()

    kefu_order_status = db.IntField()
    kefu_updatetime = db.DateTimeField()

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

    def get_rebot(type="app"):  # type: app or wap or web
        if self.crawl_source == "scqcp":
            if type == "app":
                rebot = ScqcpRebot.objects.get(telephone=self.source_account)
                return rebot
        return None

    def refresh_issued(self):
        """
        刷新出票情况
        """
        if self.status != STATUS_LOCK:
            return
        if self.crawl_source == "scqcp":
            rebot = ScqcpRebot.objects.get(telephone=self.source_account)
            tickets = rebot.request_order(self)
            if not tickets:
                self.modify(status=STATUS_CLOSED)
                rebot.remove_doing_order(self)
                issued_callback.delay(self.order_no)
                return
            code_list, msg_list = [], []
            status = tickets.values()[0]["order_status"]
            if status == "sell_succeeded":
                # 出票成功
                for tid in self.lock_info["ticket_ids"]:
                    code_list.append(tickets[tid]["code"])
                    msg_list.append("")
                self.modify(status=STATUS_ISSUE_OK, pick_code_list=code_list, pick_msg_list=msg_list)
                rebot.remove_doing_order(self)
                issued_callback.delay(self.order_no)
            elif status == "give_back_ticket":
                self.modify(status=STATUS_GIVE_BACK)
                issued_callback.delay(self.order_no)

        elif self.crawl_source == "gx84100":
            rebot = Bus100Rebot.objects.get(telephone=self.source_account)
            tickets = rebot.request_order(self)
            code_list, msg_list = [], []
            if tickets and tickets['status'] == '4':
                self.modify(status=STATUS_ISSUE_OK, pick_code_list=code_list, pick_msg_list=msg_list)
                rebot.remove_doing_order(self)
                issued_callback.delay(self.order_no)
            elif tickets['status'] == '5':
                self.modify(status=STATUS_CLOSED)
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
        """
        组成：
        年(4)+月(2)+日(2)+毫秒(6)+随机数(2)
        """
        now = datetime.now()
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
    last_login_time = db.DateTimeField(default=datetime.now)  # 最近一次登录时间
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
            self.last_login_time = datetime.now()
            self.save()
            return ret.get("msg", "fail")
        else:
            # 登陆成功
            self.is_active = True
            self.last_login_time = datetime.now()
            self.open_id = ret["open_id"]
            self.save()
            return "OK"

    @classmethod
    def login_all(cls):
        # 登陆所有预设账号
        current_app.logger.info(">>>> start to login scqcp.com:")
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
                valid_cnt += 1
        current_app.logger.info(">>>> end login scqcp.com, success %d", valid_cnt)

    def http_post(self, uri, data, user_agent="", token=""):
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
            lst = [r["id_number"], r["name"], contacter, "0", "0"]
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

    def request_order(self, order):
        if order.status in [STATUS_LOCK_FAIL, STATUS_COMMIT]:
            return
        uri = "/api/v1/ticket_lines/query_order"
        data = {"open_id": self.open_id}
        ret = self.http_post(uri, data=data)
        ticket_ids = order.lock_info["ticket_ids"]
        amount = len(ticket_ids)
        data = {}
        for d in ret["ticket_list"]:
            if d["ticket_id"] in ticket_ids:
                data[d["ticket_id"]] = d
            if len(data) >= amount:
                break
        return data


class Bus100Rebot(Rebot):
    is_encrypt = db.IntField(choices=(0, 1))
    user_agent = db.StringField()
    token = db.StringField()
    open_id = db.StringField()

    meta = {
        "indexes": ["telephone", "is_active", "is_locked"],
    }

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
            current_app.logger.error("%s %s login failed! %s", self.telephone, self.password, ret.get("returnMsg", ""))
            self.modify(is_active=False)
            return ret.get("returnMsg", "fail")

        self.modify(is_active=True, last_login_time=datetime.now(), user_agent=ua)
        return "OK"

    @classmethod
    def login_all(cls):
        """登陆所有预设账号"""
        current_app.logger.info(">>>> start to login wap.84100.com:")
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

            if bot.login() == "OK":
                valid_cnt += 1

        for tele, (pwd, openid) in accounts.items():
            if tele in has_checked:
                continue
            bot = cls(is_active=False,
                      is_locked=False,
                      telephone=tele,
                      password=pwd,
                      open_id=openid)
            bot .save()
            if bot.login() == "OK":
                valid_cnt += 1
        current_app.logger.info(">>>> end login scqcp.com, success %d", valid_cnt)

    def http_post(self, uri, data, user_agent=None, token=None):
        url = urllib2.urlparse.urljoin(Bus100_DOMAIN, uri)
        request = urllib2.Request(url)
        request.add_header('User-Agent', user_agent or self.user_agent)
        qstr = urllib.urlencode(data)
        response = urllib2.urlopen(request, qstr, timeout=10)
        ret = json.loads(response.read())
        return ret

    def recrawl_shiftid(self, line):
        """
        重新获取线路ID
        """
        queryline_url = 'http://www.84100.com/getTrainList/ajax'
        start_city_id = line.starting.station_id
        start_city_name = line.starting.station_name
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

    def request_lock_ticket(self, line, riders, contacter):
        """
        请求锁票
        startId    43100003
        planId    2380625
        name    向磊磊
        mobile    13267109876
        password
        terminalType    3
        passengerList    [{idType:"1",idNo:"429006199012280042",name:"李梦蝶",mobile:"",ticketType:"全"},{idType:"1",idNo:"429006198906100034",name:"向磊磊",mobile:"",ticketType:"全"}]
        openId    7pUGyHIri3Fjk6jEUsvv4pNfBDiX1448953063894
        isWeixin    1
        """

        url = 'http://wap.84100.com/wap/login/ajaxLogin.do'
        data = {
              "mobile": self.telephone,
              "password": self.password,
              "phone":   '',
              "code":  ''
        }
        ua = random.choice(MOBILE_USER_AGENG)
        headers = {"User-Agent": ua}
        r = requests.post(url, data=data, headers=headers)
        _cookies = r.cookies

        uri = "/wap/ticketSales/ajaxMakeOrder.do"
        passengerList = []
        for r in riders:
            tmp = {}
            tmp['idType'] = r["id_type"]
            tmp['idNo'] = r["id_number"]
            tmp['name'] = r["name"]
            tmp['mobile'] = r["telephone"]
            tmp['ticketType'] = "全票"
            passengerList.append(tmp)

        data = {
            "startId": line["carry_sta_id"],
            "planId": line["bus_num"],
            "name": contacter['name'],
            "mobile": contacter['telephone'],
            "password": '',
            "terminalType": 3,
            #"passengerList": '[{idType:"1",idNo:"429006199012280042",name:"李梦蝶1",mobile:"",ticketType:"全票"},{idType:"1",idNo:"429006198906100034",name:"向磊磊1",mobile:"",ticketType:"全票"}]',
            "passengerList": json.dumps(passengerList),
            "openId": self.open_id or 1,
            "isWeixin": 1,
        }
        url = urllib2.urlparse.urljoin(Bus100_DOMAIN, uri)
        print url
        ret = requests.post(url, data=data, cookies=_cookies)
        ret=ret.json()
        print ret
#         ret = self.http_post(uri, data)
        pay_url = ret.get('redirectPage', '')
        returnMsg = ret.get('returnMsg', '')
        if pay_url:
            ua = random.choice(MOBILE_USER_AGENG)
            headers = {"User-Agent": ua}
            r = requests.get(pay_url, verify=False,  headers=headers)
            sel = etree.HTML(r.content)
            orderNoObj = sel.xpath('//form[@id="openUnionPayForm"]/input[@id="orderNo"]/@value')
            orderAmtObj = sel.xpath('//form[@id="openUnionPayForm"]/input[@id="orderAmt"]/@value')
            if orderNoObj and orderAmtObj:
                orderNo = orderNoObj[0]
                orderAmt = orderAmtObj[0]
                ret['orderNo'] = orderNo
                ret['orderAmt'] = orderAmt
        ret['returnMsg'] = returnMsg
        print 11111111111111111111111111111111111111111
        return ret

    def request_order(self, order):
        url = 'http://wap.84100.com/wap/login/ajaxLogin.do'
        data = {
            "mobile": self.telephone,
            "password": self.password,
            "phone":   '',
            "code":  ''
        }
        ua = random.choice(MOBILE_USER_AGENG)

        headers = {"User-Agent": ua}
        r = requests.post(url, data=data, headers=headers)

        _cookies = r.cookies

        uri = "/wap/userCenter/orderDetails.do?orderNo=%s&openId=%s&isWeixin=1"%(order.raw_order_no, self.open_id or 1)
        url = urllib2.urlparse.urljoin(Bus100_DOMAIN, uri)
        r = requests.get(url, cookies=_cookies)
        sel = etree.HTML(r.content)
        orderDetailObj = sel.xpath('//div[@id="orderDetailJson"]/text()')[0]
        orderDetail = json.loads(orderDetailObj)
        orderDetail = orderDetail[0]
        return orderDetail
