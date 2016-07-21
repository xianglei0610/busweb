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
from app import db
from app.utils import md5, getRedisObj, get_redis, trans_js_str, vcode_cqky, vcode_scqcp, sha1, get_pinyin_first_litter
from app.utils import vcode_glcx
from app import rebot_log, line_log, order_log
from app.proxy import get_proxy
from pymongo import MongoClient



class AdminUser(db.Document):
    """
    后台管理员/客服
    """
    username = db.StringField(max_length=30)
    realname = db.StringField(max_length=10)
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
        if self.username in ["luojunping", "xiangleilei", "liuquan", "luocky", "august", 'chengxiaokang']:
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
    sale_line = db.DictField()              # 在售线路 {'徐州总站|xzzz|01320300001': [{'苏州|sz': {}}, ], '徐州南站|xznz|01320300002': [{'南通|nt': {}, ]}]

    meta = {
        "indexes": [
            "province",
            "city_name",
            "crawl_source",
            "is_active",
        ],
    }

    def get_open_station(self, sta_name):
        """
        获取OpenStation对象
        需要注意: 从缓存获取的内容并不一定是最新的数据
        """
        rds = get_redis("line")
        key = RK_OPEN_STATION % (self.city_name, sta_name)
        cached = rds.get(key)
        if cached:
            obj = OpenStation.from_json(cached)
        else:
            try:
                obj = OpenStation.objects.get(city=self, sta_name=sta_name)
            except:
                self.init_station()
                obj = OpenStation.objects.get(city=self, sta_name=sta_name)
            obj.add_to_cache()
        return obj

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
        new = set(map(lambda x: "%s|%s" % (x["_id"]["city_name"], x["_id"]["city_code"]), qs))
        self.modify(dest_list=old.union(new))

    def init_station(self):
        qs = Line.objects.filter(s_province=self.province, s_city_name__startswith=self.city_name) \
                         .aggregate({
                             "$group": {
                                 "_id": {
                                     "s_sta_name": "$s_sta_name",
                                     "s_sta_id": "$s_sta_id",
                                 }
                             }
                         })
        for d in qs:
            d = d["_id"]
            name, sid = d["s_sta_name"], d["s_sta_id"]
            try:
                sta_obj = OpenStation.objects.get(city=self, sta_name=name)
            except:
                sta_obj = OpenStation(city=self, sta_name=name, sta_id=str(sid), extra_info={})
                sta_obj.save()
                line_log.info("[init_station] 增加OpenStation %s %s" % (self.city_name, name))
                sta_obj.init_dest()


    def update_sale_line(self, city='', q='', extra='', crawl=''):
        '''
        徐州初始化, update_sale_line('徐州', q='s_sta_id', crawl='xyjt')
        '''
        client = MongoClient('mongodb://db:27017/')
        db = client['web12308']
        res = db.line.find({'s_city_name': city, 'crawl_source': crawl})
        sale = {}
        for x in res:
            s, e, c, eta = x['s_sta_name'], x['d_sta_name'], x.get(q, ''), x.get(extra, {})
            start = '{0}|{1}|{2}'.format(s, get_pinyin_first_litter(s), c)
            end = {'{0}|{1}'.format(e, get_pinyin_first_litter(e)): eta}
            v = sale.get(start, [])
            if v:
                if end not in v:
                    v.append(end)
                sale[start] = v
            else:
                sale[start] = [end, ]
        db.open_city.update({'city_name': city}, {'$set': {'sale_line': sale}})
        client.close()


class OpenStation(db.Document):
    """
    车站
    """
    city = db.ReferenceField(OpenCity)
    dest_info = db.ListField()              # 目的地信息 [{"name": "", "code": "", "dest_id": "", "extra_info": {自定义数据}}]
    sta_name = db.StringField(unique_with="city")             # 车站名字
    sta_id = db.StringField()
    open_time = db.StringField(default="00:00")            # 开售时间
    end_time = db.StringField(default="24:00")             # 停售时间
    advance_minutes = db.IntField(default=60)         # 分钟, 需要提前xx分钟购票
    source_weight = db.DictField()          # 源站分配权重
    crawl_source = db.StringField()         # 数据显示源
    close_status = db.IntField(default=STATION_CLOSE_NONE)   # 关闭状态: 定义见constants.py
    extra_info = db.DictField()             # 自定义数据
    create_datetime = db.DateTimeField(default=dte.now)
    line_count = db.IntField()              # 线路数, 由定时任务间隔时间刷新这个值
    day_order_count = db.DictField()        # 每天订单数和成功率, {"2016-07-08": {"count": 0, "succ_count":0}}, 由定时任务间隔时间刷新这个值


    meta = {
        "indexes": [
            "city",
            "sta_name",
            "close_status",
            ("city", "sta_name"),
        ],
    }

    def init_dest(self):
        """
        初始化目的地
        """
        city = self.city
        qs = Line.objects.filter(s_province=city.province, s_city_name__startswith=city.city_name, s_sta_name=self.sta_name) \
                         .aggregate({
                             "$group": {
                                 "_id": {
                                     "city_name": "$d_city_name",
                                     "city_code": "$d_city_code",
                                     "city_id": "$d_city_id",
                                 }
                             }
                         })
        lst = []
        for d in qs:
            d = d["_id"]
            lst.append({"name": d["city_name"], "code": d["city_code"], "dest_id": d["city_id"]})

        site_list = Line.objects.filter(s_city_name__startswith=self.city.city_name, s_sta_name=self.sta_name).distinct("crawl_source")
        self.modify(dest_info=lst, source_weight={k: 1000/(len(site_list)) for k in site_list})
        line_log.info("[init_station_dest] %s %s, %s个目的地" % (city.city_name, self.sta_name, len(lst)))
        self.clear_cache()

    def clear_cache(self):
        rds = get_redis("line")
        key = RK_OPEN_STATION % (self.city.city_name, self.sta_name)
        rds.delete(key)

    def add_to_cache(self):
        rds = get_redis("line")
        key = RK_OPEN_STATION % (self.city.city_name, self.sta_name)
        rds.set(key, self.to_json())
        rds.expire(key, 60*30)


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
            ("s_city_name","s_sta_name","d_city_name", "drv_date", "crawl_source"),
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
        left_tickets = self.left_tickets
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
                                      s_city_name=trans.get(self.s_city_name, self.s_city_name),
                                      d_city_name=trans.get(self.d_city_name, self.d_city_name),
                                      s_sta_name=self.s_sta_name,
                                      d_sta_name=self.d_sta_name,
                                      drv_datetime=self.drv_datetime)
                self.modify(compatible_lines={self.crawl_source: self.line_id, tar_source: ob.line_id})
            except Line.DoesNotExist:
                self.modify(compatible_lines={self.crawl_source: self.line_id})
            return self.compatible_lines
        elif self.s_province == "山东":
            # 畅途出发城市不带市, 畅途目的城市与365差距大
            qs = Line.objects.filter(s_city_name__startswith=self.s_city_name.rstrip(u"市"),
                                     s_sta_name=self.s_sta_name,
                                     d_sta_name=self.d_sta_name,
                                     bus_num=self.bus_num,
                                     drv_datetime=self.drv_datetime)
            d_line = {obj.crawl_source: obj.line_id for obj in qs}
            d_line.update({self.crawl_source: self.line_id})
            self.modify(compatible_lines=d_line)
            return self.compatible_lines
        elif self.s_province == "江苏":
            # 方便网，车巴达，江苏省网, 同程
            trans = {}
            qs = Line.objects.filter(s_city_name=trans.get(self.s_city_name, self.s_city_name),
                                     d_city_name=trans.get(self.d_city_name, self.d_city_name),
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
                    s_sta_name = self.s_sta_name.decode("utf-8").strip().rstrip(u"客运站")
            qs = Line.objects.filter(
                s_city_name=self.s_city_name,
                s_sta_name__startswith=unicode(s_sta_name),
                d_city_name=self.d_city_name,
                full_price=self.full_price,
                drv_datetime=self.drv_datetime)
            d_line = {obj.crawl_source: obj.line_id for obj in qs}
            d_line.update({self.crawl_source: self.line_id})
            self.modify(compatible_lines=d_line)
            return self.compatible_lines
        elif self.s_city_name == "东莞":
            # 广东省网，东莞客运
            if self.crawl_source == SOURCE_DGKY:
                trans = {
                        u"市客运北站":u"汽车北站",
                        u"市客运东站":u"东莞汽车东站",
                        u"东城汽车客运站":u"东城汽车站",
                        u"松山湖汽车客运站":u"松山湖汽车站",
                        u"长安客运站":u"长安汽车站",
                        u"虎门客运站":u"虎门汽车站",
                        u"沙田汽车客运站":u"沙田汽车站",
                        u"石龙客运站":u"石龙车站",
                        u"桥头车站":u"桥头汽车站",
                        u"东坑车站":u"东坑汽车站",
                        u"石排客运站":u"石排客运站",
                        u"樟木头振通车站":u"振通客运站",
                        u"大朗汽车客运站":u"大朗汽车客运",
                        u"清溪客运站":u"清溪车站",
                        u"塘厦车站":u"塘厦客运站",
                        u"上沙汽车客运站":u"上沙汽车站",
                        u"凤岗客运站":u"凤岗车站",
                        u"东莞市黄江汽车客运站":u"黄江车站",
                        u"东莞市南城汽车客运站":u"南城车站",
                        }
                tar_source = SOURCE_GDSW
            elif self.crawl_source == SOURCE_GDSW:
                trans = {
                        u"汽车北站":u"市客运北站",
                        u"东莞汽车东站":u"市客运东站",
                        u"东城汽车站":u"东城汽车客运站",
                        u"松山湖汽车站":u"松山湖汽车客运站",
                        u"长安汽车站":u"长安客运站",
                        u"虎门汽车站":u"虎门客运站",
                        u"沙田汽车站":u"沙田汽车客运站",
                        u"石龙车站":u"石龙客运站",
                        u"桥头汽车站":u"桥头车站",
                        u"东坑汽车站":u"东坑车站",
                        u"石排客运站":u"石排客运站",
                        u"振通客运站":u"樟木头振通车站",
                        u"大朗汽车客运":u"大朗汽车客运站",
                        u"清溪车站":u"清溪客运站",
                        u"塘厦客运站":u"塘厦车站",
                        u"上沙汽车站":u"上沙汽车客运站",
                        u"凤岗车站":u"凤岗客运站",
                        u"黄江车站":u"东莞市黄江汽车客运站",
                        u"南城车站":u"东莞市南城汽车客运站",
                        }
                tar_source = SOURCE_DGKY
            try:
                ob = Line.objects.get(crawl_source=tar_source,
                                      s_sta_name=trans.get(self.s_sta_name, self.s_sta_name),
                                      d_city_name=self.d_city_name,
                                      d_sta_name=self.d_sta_name,
                                      drv_datetime=self.drv_datetime,
                                      bus_num=self.bus_num)
                self.modify(compatible_lines={self.crawl_source: self.line_id, tar_source: ob.line_id})
            except Line.DoesNotExist:
                self.modify(compatible_lines={self.crawl_source: self.line_id})
            return self.compatible_lines
        elif self.s_city_name == "珠海":
            # 广东省网，珠海汽车购票
            if self.crawl_source == SOURCE_ZHW:
                trans = {
                        # u"上冲站":u"上冲站",
                        # u"拱北通大站":u"拱北汽车站",
                        # u"香洲长途站":u"香洲长途站",
                        # u"斗门站":u"斗门站",
                        # u"":u"岐关口岸站",
                        u"平沙站":u"珠海平沙汽车客运站",
                        u"红旗站":u"珠海红旗汽车客运站",
                        # u"三灶站":u"三灶站",
                        u"南溪站":u"珠海南溪汽车客运站",
                        # u"":u"珠海九洲港汽车客运站",
                        # u"":u"吉大配客点",
                        u"南水站":u"珠海南水汽车客运站",
                        }
                tar_source = SOURCE_GDSW
            elif self.crawl_source == SOURCE_GDSW:
                trans = {
                        # u"上冲站":u"上冲站",
                        # u"拱北汽车站":u"拱北通大站",
                        # u"香洲长途站":u"香洲长途站",
                        # u"斗门站":u"斗门站",
                        # u"":u"岐关口岸站",
                        u"珠海平沙汽车客运站":u"平沙站",
                        u"珠海红旗汽车客运站":u"红旗站",
                        # u"三灶站":u"三灶站",
                        u"珠海南溪汽车客运站南溪站":u"南溪站",
                        # u"":u"珠海九洲港汽车客运站",
                        # u"":u"吉大配客点",
                        u"珠海南水汽车客运站":u"南水站",
                        }
                tar_source = SOURCE_ZHW
            try:
                ob = Line.objects.get(crawl_source=tar_source,
                                      s_city_name=self.s_city_name,
                                      s_sta_name=trans.get(self.s_sta_name, self.s_sta_name),
                                      d_sta_name=self.d_sta_name,
                                      d_city_name=self.d_city_name,
                                      drv_datetime=self.drv_datetime)
                self.modify(compatible_lines={self.crawl_source: self.line_id, tar_source: ob.line_id})
            except Line.DoesNotExist:
                self.modify(compatible_lines={self.crawl_source: self.line_id})
            return self.compatible_lines
        elif self.s_city_name == "深圳":
            # 广东省网，深圳客货
            if self.crawl_source == SOURCE_SZKY:
                trans = {
                        u"机场汽车站":u'机场客运站',
                        u"福田站":u"深圳福田汽车客运站",
                        u"深圳北汽车站":u'深圳北汽车客运站',
                        u"南山站":u'南山汽车站',
                        u"东湖汽车站":u'东湖客运站',
                        }
                tar_source = SOURCE_GDSW
            elif self.crawl_source == SOURCE_GDSW:
                trans = {
                        u'机场客运站':u"机场汽车站",
                        u"深圳福田汽车客运站":u"福田站",
                        u'深圳北汽车客运站':u"深圳北汽车站",
                        u'南山汽车站':u"南山站",
                        u'东湖客运站':u"东湖汽车站",
                        }
                tar_source = SOURCE_SZKY
            try:
                ob = Line.objects.get(crawl_source=tar_source,
                                      s_city_name=self.s_city_name,
                                      s_sta_name=trans.get(self.s_sta_name, self.s_sta_name),
                                      d_sta_name=self.d_sta_name,
                                      d_city_name=self.d_city_name,
                                      drv_datetime=self.drv_datetime,
                                      bus_num=self.bus_num)
                self.modify(compatible_lines={self.crawl_source: self.line_id, tar_source: ob.line_id})
            except Line.DoesNotExist:
                self.modify(compatible_lines={self.crawl_source: self.line_id})
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
    pay_channel = db.StringField()  # 支付渠道, yh-银行 wx-微信 alipay-支付宝
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

    @property
    def log_name(self):
        return "%s %s" % (self.crawl_source, self.order_no)

    def change_lock_rebot(self, rebot_cls=None):
        """
        更换锁票账号
        """
        if not rebot_cls:
            rebot_cls = None
            for cls in get_rebot_class(self.crawl_source):
                if cls.is_for_lock:
                    rebot_cls = cls
                    break
        try:
            old_rebot = rebot_cls.objects.get(telephone=self.source_account)
        except rebot_cls.DoesNotExist:
            old_rebot = None

        # 已经锁票或已出票等不允许切换rebot
        if self.status not in [STATUS_WAITING_LOCK, STATUS_LOCK_RETRY]:
            return old_rebot

        # 检查释放被锁的账号
        for rebot in rebot_cls.objects.filter(is_locked=True, is_active=True):
            for no in rebot.doing_orders.keys():
                try:
                    tmp_order = Order.objects.get(order_no=no)
                except:
                    tmp_order = None
                else:
                    if tmp_order.status in [STATUS_ISSUE_FAIL, STATUS_ISSUE_SUCC, STATUS_LOCK_FAIL, STATUS_GIVE_BACK]:
                        rebot.remove_doing_order(tmp_order)

        # 释放旧rebot
        if old_rebot:
            old_rebot.remove_doing_order(self)

        # 申请新rebot
        new_rebot = rebot_cls.get_one(order=self)
        if new_rebot:
            new_rebot.add_doing_order(self)
        order_log.info("[change_lock_rebot] %s,%s=>%s" % (self.log_name, getattr(old_rebot, "telephone", ""), getattr(new_rebot, "telephone", "")))
        return new_rebot

    @property
    def source_account_pass(self):
        accounts = SOURCE_INFO[self.crawl_source]["accounts"]
        return accounts.get(self.source_account, [""])[0]

    def get_lock_rebot(self, rebot_cls=None):
        """
        获取用于锁票的rebot, 如果没有则新申请一个。
        """
        if not rebot_cls:
            cls_lst = get_rebot_class(self.crawl_source)
            rebot_cls = None
            for cls in cls_lst:
                if cls.is_for_lock:
                    rebot_cls = cls
                    break
        try:
            return rebot_cls.objects.get(telephone=self.source_account)
        except rebot_cls.DoesNotExist:
            return self.change_lock_rebot(rebot_cls=rebot_cls)

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
    ip = db.StringField(default="")

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
            bot.login()

        for tele, (pwd, openid) in accounts.items():
            if tele in has_checked:
                continue
            bot = cls(is_active=True,
                      is_locked=False,
                      telephone=tele,
                      password=pwd,)
            bot.save()
            bot.login()

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

    def add_doing_order(self, order):
        order.modify(source_account=self.telephone)
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

    @property
    def log_name(self):
        return "%s %s" % (self.crawl_source, self.telephone)

    def test_login_status(self):
        """
        验证此账号是否已经登录
        """
        is_login = 1 if  self.check_login() else 0
        msg_dict = {0: "未登录", 1: "已登录"}
        rebot_log.info("[check_login] %s, result: %s" % (self.log_name, msg_dict[is_login]))
        return is_login

    def check_login(self):
        return 1

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

class GlcxWebRebot(Rebot):
    user_agent = db.StringField()
    cookies = db.StringField()
    userid = db.StringField()

    meta = {
        "indexes": ["telephone", "is_active", "is_locked"],
        "collection": "glcxweb_rebot",
    }
    crawl_source = SOURCE_GLCX
    is_for_lock = True

    def check_login(self):
        url = 'http://www.0000369.cn/user!getCurUser.action'
        headers = {
            "User-Agent": self.user_agent,
        }
        cookies = json.loads(self.cookies)
        r = requests.get(url, headers=headers, cookies=cookies)
        soup = BeautifulSoup(r.content, "lxml")
        tel = soup.find_all('label')[0]
        if tel:
            tel = tel.get_text().strip()
        if tel == self.telephone:
            return 1
        return 0

    def login(self):
        for x in xrange(3):
            v = vcode_glcx()
            if not v:
                continue
            valid_code = v[0]
            cookies = v[1]
            params = {
                "userId": self.telephone,
                "password": self.password,
                "rand": valid_code,
                'remmber': 'on',
            }
            headers = {
                "User-Agent": self.user_agent or random.choice(BROWSER_USER_AGENT),
                "Content-Type": "application/x-www-form-urlencoded",
            }
            url = 'http://www.0000369.cn/login!login.action'
            r = requests.post(url,
                                data=urllib.urlencode(params),
                                headers=headers,
                                # allow_redirects=False,
                                cookies=cookies)
            soup = BeautifulSoup(r.content, 'lxml')
            try:
                info = soup.find('a', attrs={'onclick': 'tomyorder();'}).get_text()
                if re.findall(r'\d+', info)[0]:
                    ncookies = {
                        'JSESSIONID': dict(cookies)['JSESSIONID'],
                        'remm': 'true',
                        'user': self.telephone,
                        'pass': self.password,
                    }
                    # rebot_log.info(re.findall(r'\d+', info)[0])
                    self.modify(cookies=json.dumps(ncookies))
                    return "OK"
            except:
                pass
        return "fail"

    @classmethod
    def login_all(cls):
        # 登陆所有预设账号
        has_checked = {}
        accounts = SOURCE_INFO[cls.crawl_source]["accounts"]
        rebot_log.info(accounts)
        for bot in cls.objects:
            has_checked[bot.telephone] = 1
            if bot.telephone not in accounts:
                bot.modify(is_active=False)
                continue
            pwd = accounts[bot.telephone]
            bot.modify(password=pwd[0])
            bot.login()

        for tele, (pwd, userid) in accounts.items():
            if tele in has_checked:
                continue
            bot = cls(is_active=True,
                      is_locked=False,
                      telephone=tele,
                      password=pwd,
                      userid=userid,
                      )
            bot.save()
            bot.login()

class WmcxWebRebot(Rebot):
    user_agent = db.StringField()
    cookies = db.StringField()
    ip = db.StringField(default='')

    meta = {
        "indexes": ["telephone", "is_active", "is_locked"],
        "collection": "wmcxweb_rebot",
    }
    crawl_source = SOURCE_WMCX
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
        return "OK"

    def check_login_by_resp(self, resp):
        result = urlparse.urlparse(resp.url)
        if "login" in result.path:
            return 0
        return 1

    def check_login(self):
        undone_order_url = "http://www.wanmeibus.com/order/list.htm?billStatus=0&currentLeft=11"
        headers = {"User-Agent": self.user_agent}
        cookies = json.loads(self.cookies)
        resp = self.http_get(undone_order_url, headers=headers, cookies=cookies)
        return self.check_login_by_resp(resp)


# 代理ip, is_locked
class Hn96520WebRebot(Rebot):
    user_agent = db.StringField()
    cookies = db.StringField()
    memid = db.StringField()
    userid = db.StringField()
    sign = db.StringField()
    ip = db.StringField(default="")

    # indexes索引, 'collections'
    meta = {
        "indexes": ["telephone", "is_active", "is_locked"],
        "collection": "hn96520web_rebot",
    }
    crawl_source = SOURCE_HN96520
    is_for_lock = True

    @property
    def proxy_ip(self):
        return ""
        # rds = get_redis("default")
        # ipstr = self.ip
        # key = RK_PROXY_IP_HN96520
        # if ipstr and rds.sismember(key, ipstr):
        #     return ipstr
        # ipstr = rds.srandmember(key)
        # self.modify(ip=ipstr)
        # return ipstr

   #  @classmethod
   #  def get_one(cls, order=None):
   #      sta_bind = SOURCE_INFO[cls.crawl_source].get("station_bind", {})
   #      city_bind = SOURCE_INFO[cls.crawl_source].get("city_bind", {})
   #      query = {}
   #      if order and sta_bind:
   #          s_sta_name = order.starting_name.split(";")[1]
   #          if s_sta_name in sta_bind:
   #              query.update(telephone__in=sta_bind[s_sta_name])
   #      elif order and city_bind:
   #          s_city_name = order.starting_name.split(";")[0]
   #          if s_city_name in city_bind:
   #              query.update(telephone__in=city_bind[s_city_name])
   #      t = cls.objects._collection.find({'is_locked': True})
   #      if t.count():
   #          v = dte.now().strftime('%Y-%m-%d')
   #          for x in t:
   #              if x['doing_orders'].values().count(v) == 0:
   #                  cls.objects._collection.update({'_id': x['_id'], {'$set': {'is_locked': False}})

   #      qs = cls.objects.filter(is_active=True, is_locked=False).order_by('+last_login_time')
   #      if not qs:
   #          return
   #      sub_qs = qs.filter(**query)
   #      if sub_qs:
   #          qs = sub_qs
   #      return qs[0]

    @classmethod
    def get_one(cls, order=None):
        today = dte.now().strftime("%Y-%m-%d")
        all_accounts = set(cls.objects.filter(
            is_active=True, is_locked=False).distinct("telephone"))
        droped = set()
        for d in Order.objects.filter(status=14,
                                      crawl_source=SOURCE_HN96520,
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

    def add_doing_order(self, order):
        order.modify(source_account=self.telephone)
        d = self.doing_orders
        if order.order_no in d:
            return
        d[order.order_no] = 1
        self.modify(last_login_time=dte.now())
        self.modify(doing_orders=d)
        self.on_add_doing_order(order)

    def clear_riders(self, riders={}):
        # 默认的不能删除
        is_login = self.test_login_status()
        if not is_login:
            return
        headers = {"User-Agent": self.user_agent}
        cookies = json.loads(self.cookies)
        rider_url = 'http://www.hn96520.com/member/modify.aspx'
        r = self.http_get(rider_url, headers=headers, cookies=cookies, timeout=512)
        soup = BeautifulSoup(r.content, 'lxml')
        info = soup.find('table', attrs={'class': 'tblp shadow', 'style': True}).find_all('tr', attrs={'id': True})
        for x in info:
            uid = x.get('id').strip()
            uid = str(re.search(r'\d+', uid).group(0))
            if uid in riders or not riders:
                delurl = 'http://www.hn96520.com/member/takeman.ashx?action=DeleteTakeman&id={0}&memberid={1}'.format(uid, self.memid)
                # rebot_log.info(delurl)
                self.http_get(delurl, headers=headers, cookies=cookies, timeout=2048)

    def add_riders(self, order):
        url = "http://www.hn96520.com/member/modify.aspx"
        headers = {
            'User-Agent': self.user_agent,
            "Referer": "http://www.hn96520.com/member/modify.aspx",
        }
        cookies = json.loads(self.cookies)
        r = self.http_get(url, headers=headers, cookies=cookies)
        soup = BeautifulSoup(r.content, "lxml")
        userid = soup.select_one("#userid").text

        id_lst = []
        for rider in order.riders:
            dom = soup.find("input", attrs={"value": rider["id_number"]})
            if dom:
                id_lst.append(dom.get("id").lstrip("takemancardid"))
            else:
                name = rider.get('name', '')
                cardid = rider.get('id_number', '')
                sel = rider.get('telephone', '')
                url = 'http://www.hn96520.com/member/takeman.ashx?action=AppendTakeman&memberid={0}&name={1}&cardid={2}&sel={3}'.format(userid, name, cardid, sel)
                r = self.http_get(url, headers=headers, cookies=cookies)
                id_lst.append(r.content)
        return id_lst

    def check_login(self):
        # self.is_locked = True
        # self.save()
        undone_order_url = "http://www.hn96520.com/member/changeselfinfo.aspx"
        headers = {"User-Agent": self.user_agent}
        cookies = json.loads(self.cookies)
        r = self.http_get(undone_order_url, headers=headers, cookies=cookies)
        soup = BeautifulSoup(r.content, "lxml")
        tel = soup.select_one("#txtHandset")
        if tel:
            tel = tel.get("value")
        if tel == self.telephone:
            return 1
        return 0

    # 初始化帐号
    def login(self):
        ua = random.choice(BROWSER_USER_AGENT)
        self.last_login_time = dte.now()
        self.user_agent = ua
        self.is_active = True
        self.cookies = "{}"
        self.save()
        return "OK"

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
            pwd = accounts[bot.telephone]
            bot.modify(password=pwd[0])
            bot.login()

        for tele, (pwd, sign, userid) in accounts.items():
            if tele in has_checked:
                continue
            bot = cls(is_active=True,
                      is_locked=False,
                      telephone=tele,
                      password=pwd,
                      sign=sign,
                      userid=userid,
                      )
            bot.save()
            bot.login()


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

    # 初始化帐号
    def login(self):
        ua = random.choice(BROWSER_USER_AGENT)
        self.last_login_time = dte.now()
        self.user_agent = ua
        self.is_active = True
        self.cookies = "{}"
        self.save()
        return "OK"


class XyjtWebRebot(Rebot):
    user_agent = db.StringField()
    cookies = db.StringField()
    meta = {
        "indexes": ["telephone", "is_active", "is_locked"],
        "collection": "xyjtweb_rebot",
    }
    crawl_source = SOURCE_XYJT
    is_for_lock = True

    def clear_riders(self, riders={}):
        pass

    def add_riders(self, order):
        pass

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
        return "OK"

class ZhwWebRebot(Rebot):
    user_agent = db.StringField()
    cookies = db.StringField()
    meta = {
        "indexes": ["telephone", "is_active", "is_locked"],
        "collection": "zhwweb_rebot",
    }
    crawl_source = SOURCE_ZHW
    is_for_lock = True

    # 初始化帐号
    def login(self):
        ua = random.choice(BROWSER_USER_AGENT)
        self.last_login_time = dte.now()
        self.user_agent = ua
        self.is_active = True
        self.cookies = "{}"
        self.save()
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

    def check_login(self):
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
        return "fail"

    def check_login(self):
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


class GdswRebot(Rebot):
    user_agent = db.StringField()
    token = db.StringField()
    mobile = db.StringField()

    meta = {
        "indexes": ["telephone", "is_active", "is_locked"],
        "collection": "gdsw_rebot",
    }
    crawl_source = SOURCE_GDSW
    is_for_lock = True

    @property
    def proxy_ip(self):
        return ""

    def on_add_doing_order(self, order):
        self.modify(is_locked=True)

    def on_remove_doing_order(self, order):
        self.modify(is_locked=False)

    def get_signature(self, timestamp, nonce):
        secret = "561768DB-0A89-451B-8F64-69D0A9422F1Da"
        lst = [timestamp, nonce, secret]
        lst.sort()
        return sha1("".join(lst))

    def login(self):
        if self.test_login_status():
            return "OK"
        url = "http://183.6.161.195:9000/api/Auth/GetAppToken"
        ts = str(int(time.time()))
        rd = str(random.random())
        params = dict(
            username=self.telephone,
            password=self.password,
            channelid="null",
            devicetype="android",
            signature=self.get_signature(ts, rd),
            timestamp=ts,
            nonce=rd,
            appid="andio_95C429257",
        )
        ua = random.choice(MOBILE_USER_AGENG)
        url = "%s?%s" % (url, urllib.urlencode(params))
        r = self.http_get(url, headers={"User-Agent": ua})
        res = r.json()
        token = res["access_token"]
        if token:
            self.modify(token=token, user_agent=ua, last_login_time=dte.now())
            return "OK"
        return "fail"

    def check_login(self):
        user_url = "http://183.6.161.195:9000/api/Subscriber/Get?token=%s" % self.token
        headers = {
            "User-Agent": self.user_agent,
            "Content-Type": "application/json;charset=UTF-8",
        }
        r = self.http_get(user_url, headers=headers)
        try:
            res = r.json()
        except:
            return 0
        if not res["success"]:
            return 0
        if self.telephone not in [res["data"]["name"],res["data"]["mobile"]]:
            return 0
        self.modify(mobile=res["data"]["mobile"])
        return 1

    def clear_riders(self):
        headers = {
            "User-Agent": self.user_agent,
            "Content-Type": "application/json;charset=UTF-8",
        }
        del_url = "http://183.6.161.195:9000/api/Contact/Delete?token=%s" % self.token
        for pk in self.get_riders().values():
            try:
                self.http_post(del_url, headers=headers, data={"id": pk})
            except:
                pass


    def get_riders(self):
        if not self.test_login_status():
            raise Exception("%s账号未登录" % self.telephone)
        headers = {
            "User-Agent": self.user_agent,
            "Content-Type": "application/json;charset=UTF-8",
        }
        query_url = "http://183.6.161.195:9000/api/Contact/Get?token=%s" % self.token
        r = self.http_get(query_url, headers=headers)
        res = r.json()
        cardtoid = {}
        if not res["success"]:
            return {}
        for d in res["data"]:
            cardtoid[d["certno"]] = d["id"]
        return cardtoid

    def add_riders(self, order):
        add_url = "http://183.6.161.195:9000/api/Contact/Add?token=%s" % self.token
        headers = {
            "User-Agent": self.user_agent,
            "Content-Type": "application/json;charset=UTF-8",
        }
        id_lst = []
        exists_lst = {}
        for c in order.riders:
            params = {
                "certno": c["id_number"],
                "certtype": "1",
                "mobile": c["telephone"] or order.contact_info["telephone"],
                "name": c["name"],
                "passengertype": "1"
            }
            r = self.http_post(add_url, headers=headers, data=urllib.urlencode(params))
            res = r.json()
            if "已存在相同证件号的联系人" in res["errorMsg"]:
                if not exists_lst:
                    exists_lst = self.get_riders()
                id_lst.append(exists_lst[c["id_number"].upper()])
            else:
                id_lst.append(res["data"])
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

    def check_login(self):
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
#         return ""
        rds = get_redis("default")
        ipstr = self.ip
        if ipstr and rds.sismember(RK_PROXY_IP_SCQCP, ipstr):
            return ipstr
        ipstr = rds.srandmember(RK_PROXY_IP_SCQCP)
        self.modify(ip=ipstr)
        return ipstr

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

    def check_login(self):
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
#         return ""
        rds = get_redis("default")
        ipstr = self.ip
        if ipstr and rds.sismember(RK_PROXY_IP_SCQCP, ipstr):
            return ipstr
        ipstr = rds.srandmember(RK_PROXY_IP_SCQCP)
        self.modify(ip=ipstr)
        return ipstr

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
                return "OK"
            else:
                msg = res["msg"]
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
            return "fail"

    def check_login(self):
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

    def check_login(self):
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
            return "OK"
        else:
            self.modify(is_active=False)
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
        return "OK"

    def check_login(self):
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

    def check_login(self):
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


class Lvtu100AppRebot(Rebot):
    user_agent = db.StringField(default="okhttp/2.5.0")
    member_id = db.IntField()
    token = db.StringField()

    meta = {
        "indexes": ["telephone", "is_active", "is_locked"],
        "collection": "lvtu100app_rebot",
    }
    crawl_source = SOURCE_LVTU100
    is_for_lock = True

    def post_data_templ(self, custom):
        data = {
            "appid": "lvtu100.andorid",
            "timestamp": str(int(time.time())),
            "format": "json",
            "version": "1.0",
        }
        data.update(custom)
        key_lst = filter(lambda x: data[x], data.keys())
        key_lst.sort()
        data["sign"]= md5("".join("%s%s" % (k, data[k]) for k in key_lst) + "0348ba1cbbfa0fa9ca627394e999fea5")
        return data

    def post_header(self):
        headers = {
            "User-Agent": "okhttp/2.5.0",
            "Content-Type": "application/x-www-form-urlencoded",
        }
        return headers

    def login(self):
        if self.test_login_status():
            return "OK"

        url = "http://api.lvtu100.com/uc/member/login"
        params = {
            "Login_name": self.telephone,
            "Pw": self.password,
            "Source":"android"
        }
        params = {"logininfo": json.dumps(params)}
        params = self.post_data_templ(params)
        r = self.http_post(url, headers=self.post_header(), data=urllib.urlencode(params))
        ret = r.json()
        if ret["code"] == 0:
            self.modify(token=ret["data"]["token"], member_id=ret["data"]["member_id"], last_login_time=dte.now())
            return "OK"
        return "fail"

    def test_login_status(self):
        url = "http://api.lvtu100.com/uc/member/getmember"
        params = {
            "token": self.token,
            "member_id": self.member_id,
        }
        params = {"data": json.dumps(params)}
        params = self.post_data_templ(params)
        r = self.http_post(url, headers=self.post_header(), data=urllib.urlencode(params))
        ret = r.json()
        if ret["code"] != 0:
            return 0
        if ret["data"]["mobile"] == self.telephone:
            return 1
        return 0

    def clear_riders(self):
        is_login = self.test_login_status()
        if not is_login:
            return
        url = "http://api.lvtu100.com/uc/member/deletepurchase"
        for idx in self.get_riders().values():
            params = [{
                "addr_id": idx,
                "member_id": self.member_id,
            }]
            params = {"data": json.dumps(params)}
            params = self.post_data_templ(params)
            self.http_post(url, headers=self.post_header(), data=urllib.urlencode(params))

    def get_riders(self):
        url = "http://api.lvtu100.com/uc/member/getpurchase"
        params = {
            "token": self.token,
            "member_id": self.member_id,
        }
        params = {"data": json.dumps(params)}
        params = self.post_data_templ(params)
        r = self.http_post(url, headers=self.post_header(), data=urllib.urlencode(params))
        ret = r.json()
        idcard_to_id = {d["idcard"]: d["addr_id"] for d in ret["data"]}
        return idcard_to_id

    def add_riders(self, order):
        url = "http://api.lvtu100.com/uc/member/savepurchase"
        id_lst = []
        exists_lst = {}
        for r in order.riders:
            params = [{
                "addr_id":"",
                "member_id": self.member_id,
                "mobile": r["telephone"],
                "idcard": r["id_number"],
                "name": r["name"],
            }]
            params = {"data": json.dumps(params)}
            params = self.post_data_templ(params)
            resp = self.http_post(url, headers=self.post_header(), data=urllib.urlencode(params))
            ret = resp.json()
            if "已添加过该身份证号" in ret["message"]:
                if not exists_lst:
                    exists_lst = self.get_riders()
                id_lst.append(exists_lst[r["id_number"]])
            else:
                id_lst.append(ret["data"])
        return id_lst


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
        return "OK"

    def check_login_by_resp(self, resp):
        result = urlparse.urlparse(resp.url)
        if "login" in result.path:
            return 0
        return 1

    def check_login(self):
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
            return "OK"
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
            return "OK"
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
    user_info = db.DictField()

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
        self.modify(is_locked=True)

    def on_remove_doing_order(self, order):
        self.modify(is_locked=False)

    def login(self, valid_code="", headers=None, cookies=None):
        if not headers:
            headers = {}
        if not cookies:
            cookies = {}
        vcode_flag = False
        if not valid_code:
            login_form = "http://www.96096kp.com/CusLogin.aspx"
            valid_url = "http://www.96096kp.com/ValidateCode.aspx"
            headers = {"User-Agent": random.choice(BROWSER_USER_AGENT)}
            r = self.http_get(login_form, headers=headers, cookies=cookies)
            cookies.update(dict(r.cookies))
            for i in range(3):
                r = self.http_get(valid_url, headers=headers, cookies=cookies)
                if "image" not in r.headers.get('content-type'):
                    self.modify(ip="")
                else:
                    break
            cookies.update(dict(r.cookies))
            valid_code = vcode_cqky(r.content)
            vcode_flag = True

        ret = "fail"
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
            r = self.http_post(login_url, data=urllib.urlencode(params), headers=headers, cookies=cookies)
            res = json.loads(trans_js_str(r.content))
            success = res.get("success", True)
            if success:     # 登陆成功
                cookies.update(dict(r.cookies))
                self.modify(cookies=json.dumps(cookies), is_active=True)
                if self.test_login_status():
                    self.modify(user_info=res)
                    ret = "OK"
                else:
                    ret = "check_fail"
            else:
                msg = res["msg"]
                if u"用户名或密码错误" in msg:
                    ret = "invalid_pwd"
                elif u"请正确输入验证码" in msg or u"验证码已过期" in msg:
                    ret = "invalid_code"
                else:
                    ret = msg
        else:
            ua = random.choice(BROWSER_USER_AGENT)
            self.last_login_time = dte.now()
            self.user_agent = ua
            self.is_active = True
            self.cookies = "{}"
            self.save()
            ret = "create"
        rebot_log.info("[login]%s,result:%s,ip:%s,cookie:%s,vcode:%s", self.log_name, ret, self.proxy_ip, cookies, "auto" if vcode_flag else "manual")
        return ret

    def check_login(self):
        user_url = "http://www.96096kp.com/UpdateMember.aspx"
        headers = {
            "User-Agent": self.user_agent,
            "Referer": "http://www.96096kp.com/TicketMain.aspx",
            "Origin": "http://www.96096kp.com",
        }
        cookies = json.loads(self.cookies)
        r = self.http_get(user_url, headers=headers, cookies=cookies)
        soup = BeautifulSoup(r.content, "lxml")
        tel_dom = soup.select_one("#ctl00_FartherMain_txt_Mobile")
        if not tel_dom:
            self.modify(ip="")
            return 0

        tel = tel_dom.get("value")
        if tel != self.telephone:
            if tel: # 问题代理ip嫌疑
                get_proxy("cqky").set_black(self.proxy_ip)
            self.modify(cookies="{}", ip="")
            return 0
        return 1


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
        s = "AccountID=%s&ReqTime=%s&ServiceName=%s&Version=%s" % (account_id, stime, service_name, version)
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
            return "OK"
        else:
            self.update(is_active=False)
        return "fail"

    def check_login(self):
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
            return "OK"
        else:
            self.modify(is_active=True)
            return "fail"

    def check_login_by_resp(self, resp):
        result = urlparse.urlparse(resp.url)
        if result.netloc == u"passport.ly.com":
            return 0
        return 1

    def check_login(self):
        user_url = "http://member.ly.com/Member/MemberInfomation.aspx"
        headers = {
            "User-Agent": self.user_agent or random.choice(BROWSER_USER_AGENT)}
        cookies = json.loads(self.cookies)
        resp = self.http_get(user_url, headers=headers, cookies=cookies, verify=False)
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

    def check_login(self):
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
        self.modify(is_locked=True)

    def on_remove_doing_order(self, order):
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
            return "OK"
        else:
            return "fail"

    def check_login(self):
        try:
            user_url = "http://www.gzsqcp.com//com/yxd/pris/openapi/detailPersonalData.action"
            headers = {"User-Agent": self.user_agent}
            cookies = json.loads(self.cookies)
            data = {}
            res = requests.post(user_url, data=data, headers=headers, cookies=cookies)
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
        self.modify(is_locked=True)

    def on_remove_doing_order(self, order):
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
            self.test_login_status()
            return "OK"
        else:
            return "fail"

    def check_login(self):
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
            valid_cnt += 1

    def check_login(self):
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
        self.modify(is_locked=True)

    def on_remove_doing_order(self, order):
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
            return "OK"
        else:
            return "fail"

    def check_login(self):
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
        self.modify(is_locked=True)

    def on_remove_doing_order(self, order):
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
            return "OK"
        else:
            return "fail"

    def check_login(self):
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
    user_agent = db.StringField(default="Apache-HttpClient/UNAVAILABLE (java 1.4)")
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
        return ''
#         rds = get_redis("default")
#         ipstr = self.ip
#         if ipstr and rds.sismember(RK_PROXY_IP_E8S, ipstr):
#             return ipstr
#         ipstr = rds.srandmember(RK_PROXY_IP_E8S)
#         self.modify(ip=ipstr)
#         return ipstr

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


class E8sWebRebot(Rebot):
    user_agent = db.StringField()
    user_id = db.StringField()
    ip = db.StringField(default="")
    cookies = db.StringField()

    meta = {
        "indexes": ["telephone", "is_active", "is_locked"],
        "collection": "e8sweb_rebot",
    }
    crawl_source = SOURCE_E8S
    is_for_lock = False

    @property
    def proxy_ip(self):
        return ''
#         return '192.168.1.53:8888'
#         rds = get_redis("default")
#         ipstr = self.ip
#         if ipstr and rds.sismember(RK_PROXY_IP_E8S, ipstr):
#             return ipstr
#         ipstr = rds.srandmember(RK_PROXY_IP_E8S)
#         self.modify(ip=ipstr)
#         return ipstr

    def http_header(self, ua=""):
        return {
            "Charset": "UTF-8",
            "User-Agent": self.user_agent or ua,
        }

    def login(self):
        ua = random.choice(BROWSER_USER_AGENT)
        headers = self.http_header(ua)
        data = {
            "pwd": self.password,
            "userName": self.telephone
        }

        url = "http://www.bawangfen.cn/bwf/doLogin.htm"
        cookies = {}

        headers.update({"X-Requested-With": "XMLHttpRequest",
                        "Referer": "http://www.bawangfen.cn/bwf/login.htm",
                        "Content-Type": "application/x-www-form-urlencoded; charset=UTF-8",
                        })
        r = self.http_post(url, data=urllib.urlencode(data), cookies=cookies, headers=headers)
        cookies.update(dict(r.cookies))
        ret = r.json()
        if ret["flag"] == 'true' and ret['userCode'] == self.telephone:
            # 登陆成功
            self.is_active = True
            self.last_login_time = dte.now()
            self.cookies = json.dumps(cookies)
            self.user_agent = self.user_agent or ua
            self.save()
            return "OK"
        else:
            # 登陆失败
            self.is_active = False
            self.last_login_time = dte.now()
            self.cookies = '{}'
            self.save()
            return ret.get("msg", "fail")

    def check_login(self):
        try:
            check_url = "http://www.bawangfen.cn/bwf/verifyLogin.htm"
            headers = self.http_header()
            headers.update({"X-Requested-With": "XMLHttpRequest",
                            "Referer": "http://www.bawangfen.cn/bwf/",
                            "Content-Type": "application/x-www-form-urlencoded; charset=UTF-8",
                            })
            cookies = json.loads(self.cookies)
            data = {}
            res = self.http_post(check_url, data=data, headers=headers, cookies=cookies)
            res = res.json()
            if self.telephone == res.get('userName', ''):
                return 1
            else:
                return 0
        except:
            return 0


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
        self.modify(is_locked=True)

    def on_remove_doing_order(self, order):
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
            return "OK"
        else:
            return "fail"

    def check_login(self):
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

    def check_login(self):
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
        self.modify(is_locked=True)

    def on_remove_doing_order(self, order):
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
                self.test_login_status()
                return "OK"
            else:
                return "fail"
        else:
            return "fail"

    def check_login(self):
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
        self.modify(is_locked=True)

    def on_remove_doing_order(self, order):
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
                return "OK"
            else:
                return "fail"
        else:
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
                line_id = md5("%(s_city_name)s-%(d_city_name)s-%(drv_datetime)s-%(s_sta_name)s-%(d_sta_name)s-%(crawl_source)s" % line_id_args)
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

    def clear_riders(self):
        url = "http://www.bus365.com/passenger/getPiList/0"
        param = {
            "page": "1",
            "size": "100",
            "userId": self.user_id,
            "token": json.dumps({"clienttoken": self.client_token, "clienttype":"android"}),
            "clienttype": 'android',
            "usertoken": self.client_token
        }
        url = url + '?'+urllib.urlencode(param)
        headers = self.http_header()
        try:
            res = self.http_get(url, headers=headers)
            res = res.json()
            for i in res.get('pis', []):
                del_url = "http://www.bus365.com/passenger/deletePi/0"
                param.update({"deviceid": self.deviceid, "piIds": i['id']})
                res = self.http_post(del_url, data=param, headers=headers)
                res = res.json()
        except:
            pass


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

    def check_login(self):
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
        self.modify(is_locked=True)

    def on_remove_doing_order(self, order):
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

    def check_login(self):
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
        self.modify(cookies="{}")
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
                return "OK"
            else:
                msg = res["msg"]
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


class SzkyWebRebot(Rebot):
    user_agent = db.StringField()
    cookies = db.StringField(default="{}")
    username = db.StringField(default="")
    user_id = db.StringField(default="")
    ip = db.StringField(default="")

    meta = {
        "indexes": ["telephone", "is_active", "is_locked", "ip"],
        "collection": "szkyweb_rebot",
    }
    crawl_source = SOURCE_SZKY
    is_for_lock = True

    @property
    def proxy_ip(self):
        return ''
#         rds = get_redis("default")
#         ipstr = self.ip
#         if ipstr and rds.sismember(RK_PROXY_IP_SZKY, ipstr):
#             return ipstr
#         ipstr = rds.srandmember(RK_PROXY_IP_SZKY)
#         self.modify(ip=ipstr)
#         return ipstr

    @classmethod
    def get_one(cls, order=None):
        today = dte.now().strftime("%Y-%m-%d")
        all_accounts = set(cls.objects.filter(
            is_active=True, is_locked=False).distinct("telephone"))
        droped = set()
        if order:
            for d in Order.objects.filter(status=14,
                                          crawl_source=SOURCE_SZKY,
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
        rebot_log.info("[szky] %s locked", self.telephone)
        self.modify(is_locked=True)

    def on_remove_doing_order(self, order):
        rebot_log.info("[szky] %s unlocked", self.telephone)
        self.modify(is_locked=False)

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

        for tele, (pwd, username) in accounts.items():
            if tele in has_checked:
                continue
            bot = cls(is_active=True,
                      is_locked=False,
                      telephone=tele,
                      password=pwd,
                      username=username,
                      user_agent=random.choice(BROWSER_USER_AGENT))
            bot.save()
            msg = bot.login()
            rebot_log.info("[login_all] %s %s %s",
                           cls.crawl_source, bot.telephone, msg)

    def login(self, valid_code="", headers=None, cookies=None):
        if not headers:
            headers = {}
        if not cookies:
            cookies = {}
        vcode_flag = False
        if not valid_code:
            login_form = "http://124.172.118.225/UserData/UserCmd.aspx"
            valid_url = "http://124.172.118.225/ValidateCode.aspx"
            headers = {"User-Agent": random.choice(BROWSER_USER_AGENT)}
            r = self.http_get(login_form, headers=headers, cookies=cookies)
            cookies.update(dict(r.cookies))
            for i in range(3):
                r = self.http_get(valid_url, headers=headers, cookies=cookies)
                if "image" not in r.headers.get('content-type'):
                    self.modify(ip="")
                else:
                    break
            cookies.update(dict(r.cookies))
            valid_code = vcode_cqky(r.content)
            vcode_flag = True

        if valid_code:
            headers = {
                "User-Agent": headers.get("User-Agent", "") or self.user_agent,
                "Referer": "http://124.172.118.225/User/Default.aspx",
                "Content-Type": "application/x-www-form-urlencoded; charset=UTF-8",
                "X-Requested-With": "XMLHttpRequest"
            }
            params = {
                "loginID": self.telephone,
                "loginPwd": self.password,
                "getInfo": 1,
                "loginValid": valid_code,
                "cmd": "login",
            }
            login_url = "http://124.172.118.225/UserData/UserCmd.aspx"
            r = self.http_post(login_url, data=urllib.urlencode(params), headers=headers, cookies=cookies)
            res = json.loads(trans_js_str(r.content))
            success = res.get("success", True)
            if success:     # 登陆成功
                cookies.update(dict(r.cookies))
                if res["F_Code"] != self.telephone:
                    return "fail"
                self.modify(cookies=json.dumps(cookies), is_active=True, user_id=res['F_Guid'])
                rebot_log.info("[szky]登陆成功, %s vcode_flag:%s cookeis:%s", self.telephone, vcode_flag, cookies)
                return "OK"
            else:
                msg = res["msg"]
                rebot_log.info("[szky]%s %s vcode_flag:%s",
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

    def check_login(self):
        user_url = "http://124.172.118.225/User/Default.aspx"
        headers = {
            "User-Agent": self.user_agent,
        }
        cookies = json.loads(self.cookies)
        r = self.http_get(user_url, headers=headers, cookies=cookies)
        content = r.content
        if not isinstance(content, unicode):
            content = content.decode("utf8")
        if self.username in content:
            return 1
        self.modify(cookies="{}")
        return 0

    def query_code(self, headers):
        cookies = {}
        valid_code = ''
        if not valid_code:
            login_form = "http://124.172.118.225/UserData/UserCmd.aspx"
            valid_url = "http://124.172.118.225/ValidateCode.aspx"
            r = self.http_get(login_form, headers=headers, cookies=cookies)
            cookies.update(dict(r.cookies))
            for i in range(3):
                r = self.http_get(valid_url, headers=headers, cookies=cookies)
                if "image" not in r.headers.get('content-type'):
                    self.modify(ip="")
                else:
                    break
            cookies.update(dict(r.cookies))
            valid_code = vcode_cqky(r.content)

        if valid_code:
            headers = {
                "User-Agent": headers.get("User-Agent", ""),
                "Referer": "http://124.172.118.225/User/Default.aspx",
                "Content-Type": "application/x-www-form-urlencoded; charset=UTF-8",
                "X-Requested-With": "XMLHttpRequest"
            }
            params = {
                "loginID": self.telephone,
                "loginPwd": self.password,
                "getInfo": 1,
                "loginValid": valid_code,
                "cmd": "login",
            }
            login_url = "http://124.172.118.225/UserData/UserCmd.aspx"
            r = self.http_post(login_url, data=urllib.urlencode(params), headers=headers, cookies=cookies)
            ret = json.loads(trans_js_str(r.content))
            success = ret.get("success", True)
            res = {}
            if success:     # 登陆成功
                cookies.update(dict(r.cookies))
                if ret["F_Code"] != self.telephone:
                    res.update({'status': 1})
                    return res
                res.update({'status': 0, 'cookies': cookies, 'valid_code':valid_code})
                return res
            else:
                res.update({'status': 1})
                return res


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

    def check_login(self):
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
            self.modify(is_active=False)
            return ret.get("returnMsg", "fail")
        self.modify(is_active=True, last_login_time=dte.now(), user_agent=ua)
        return "OK"

    @classmethod
    def login_all(cls):
        """登陆所有预设账号"""
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

        for tele, (pwd, openid) in accounts.items():
            if tele in has_checked:
                continue
            bot = cls(is_active=True,
                      is_locked=False,
                      telephone=tele,
                      password=pwd,
                      open_id=openid)
            bot.save()
            valid_cnt += 1

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
                line_id = md5("%s-%s-%s-%s-%s" % (payload['startName'], payload['endName'], drv_datetime, str(banci), 'bus100'))
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
    return _rebot_class.get(source, [])
