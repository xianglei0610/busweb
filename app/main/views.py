# -*- coding:utf-8 -*-
import threading
import urllib2

from app import app
from app.constants import *
from datetime import datetime
from flask import request, jsonify, current_app
from mongoengine import Q
from app.main import main
from app.models import Line, Starting, Destination, ScqcpRebot, Order
import json


@main.route('/startings/query', methods=['POST'])
def query_starting():
    """
    出发地查询

    返回:
    {
        "code": 1,
        "message": "ok"
        data: [{
            "province": "广东",             # 省份
            "city_list":[{
                "city_name": "深圳",        # 城市名
                "city_code": "SZ",          # 城市拼音缩写
                "pre_sell_days": 6,         # 预售期
                "open_time": "07:00:00",    # 开放售票时间
                "end_time": "23:00:00",     # 结束售票时间
                "is_pre_sell": 0,           # 是否可预订
                "advance_order_time": 120,  # 至少提前多久订票，单位(分钟)
            }]
        },]
    }
    """
    province_data = {}
    distinct_data = {}
    for obj in Starting.objects:
        if (obj.province_name, obj.city_name) in distinct_data:
            continue
        distinct_data[(obj.province_name, obj.city_name)] = 1

        if obj.province_name not in province_data:
            province_data[obj.province_name] = {}
            province_data[obj.province_name]["province"] = obj.province_name
            province_data[obj.province_name]["city_list"] = []

        item = {
            "city_name": obj.city_name,
            "city_code": obj.city_pinyin_prefix,
            "is_pre_sell": obj.is_pre_sell,
            "pre_sell_days": obj.pre_sell_days,
            "open_time": obj.open_time,
            "end_time": obj.end_time,
            "advance_order_time": obj.advance_order_time,
        }
        province_data[obj.province_name]["city_list"].append(item)

    return jsonify({"code": 1, "message": "OK", "data": province_data.values()})


@main.route('/destinations/query', methods=['POST'])
def query_destination():
    """
    Input:
        - starting_name: 出发地名字

    Return:
        {
            "code": 1,
            "message": "OK",
            "data":[
                "安吉|aj","安平|ap","周庄(江苏昆山)|zz(jsks)"
            ],
        }
    """
    starting_name = request.form.get("starting_name")
    dest_list = Destination.objects(starting__in=Starting.objects(city_name__startswith=unicode(starting_name)))
    data = map(lambda obj: "%s|%s" % (obj.station_name or obj.city_name,
               obj.station_pinyin_prefix or obj.city_pinyin_prefix), dest_list)
    return jsonify({"code": 1, "message": "OK", "data": data})

@main.route('/lines/query', methods=['POST'])
def query_line():
    """
    Input:
        - starting_name: 出发地名字
        - destination_name: 目的地名字
        - start_date: 出发日期

    Return:
        {
            "code": 1,
            "message": "OK",
            "data": [
                "line_id": "1111"                   # 线路ID
                "starting_city": "成都"             # 出发城市
                "starting_station": "南站",         # 出发站
                "destination_city": "重庆",         # 目的地城市
                "destination_station": "西站",      # 目的地站
                "bus_num": "Y100",                  # 车次
                "drv_date": "2015-11-11",           # 开车日期
                "drv_time": "12:00",                # 开车时间
                "vehicle_type": "普快",             # 车型
                "full_price": 10,                 # 全价
                "half_price": 5,                  # 半价
                "can_order": 1,                     # 是否可预订
                "fee": "1",                         # 手续费
                ""
            ]
        }
    """

    starting_name = request.form.get("starting_name")
    dest_name = request.form.get("destination_name")
    start_date = request.form.get("start_date")
    qs_starting = Starting.objects(Q(city_name__startswith=starting_name)|Q(station_name__startswith=starting_name))
    qs_dest = Destination.objects(Q(city_name__startswith=dest_name)|Q(station_name__startswith=dest_name))
    qs_line = Line.objects(starting__in=qs_starting, destination__in=qs_dest, drv_date=start_date)

    def _extract_data(obj):
        return {
            "line_id": obj.line_id,
            "starting_city": obj.starting.city_name,
            "starting_station": obj.starting.station_name,
            "destination_city": obj.destination.city_name,
            "destination_station": obj.destination.station_name,
            "bus_num": obj.bus_num,
            "drv_date": obj.drv_date,
            "drv_time": obj.drv_time,
            "vehicle_type": obj.vehicle_type,
            "full_price": obj.full_price,
            "half_price": obj.half_price,
            "can_order": obj.can_order,
            "fee": obj.fee,
        }
    data = map(lambda obj: _extract_data(obj), qs_line)
    return jsonify({"code": 1, "message": "OK", "data": data})


@main.route('/orders/submit', methods=['POST'])
def submit_order():
    """
    提交订单
    Input:
        - line_id: "111"                        # 线路ID
        - order_price: 11                       # 订单金额(总票价)
        - contacter: "名字|手机号|身份证号"     # 联系人
        - riders: 名字|手机号|证件号$名字2|手机号2|证件号2
        - callback_url: "http://xxx"            # 锁票成功回调地址

    Return:
        {
           "code": 1,
           "message": "submit order success!"
           "data":{
               "order_no": xxxxxx,
            }
        }
    """
    line = Line.objects.get(line_id=request.form.get("line_id"))
    ctr_name, ctr_phone, ctr_idcard = request.form.get("contacter").split("|")
    order_price = float(request.form.get("order_price"))
    rider_list = []
    for s in request.form.get("riders").split("$"):
        name, tele, idcard = s.split("|")
        rider_list.append({"name": name, "telephone": tele, "idcard": idcard})

    if not rider_list:
        abort(400)
    ticket_amount = len(rider_list)
    return_url = request.form.get("callback_url")

    # 核对票价
    pass

    order = Order()
    order.order_no = Order.generate_order_no()
    order.status = STATUS_COMMIT
    order.order_price = order_price
    order.create_date_time = datetime.now()
    order.line = line
    order.ticket_price = line.full_price
    order.ticket_amount = ticket_amount
    order.ticket_fee = line.fee
    order.contacter_phone = ctr_phone
    order.contacter_name = ctr_name
    order.contacter_idcard = ctr_idcard
    order.riders = rider_list
    order.crawl_source = line.crawl_source
    order.save()

    t = threading.Thread(target=async_lock_ticket, args=(order.order_no, return_url))
    t.start()

    return jsonify({"code": 1, "message": "submit order success!", "data": {"order_no": order.order_no}})


def async_lock_ticket(order_no, notify_url):
    """
    请求源网站锁票

    Return:
        expire_time: 122112121,     # 订单过期时间戳
        total_price: 322，          # 车票价格
    """
    order = Order.objects.get(order_no=order_no)

    if order.crawl_source == "scqcp":
        rebot = ScqcpRebot.objects.first()
        msg = rebot.request_lock_ticket(order)
        data = []
        if not msg:
            total_price = 0
            for ticket in order.lock_info["ticket_list"]:
                total_price += (ticket["server_price"], ticket["real_price"])
            data = {
                "expire_time": order.lock_info["expire_time"],
                "total_price": total_price,
            }
            json_str = json.dumps({"code": 1, "message": "OK", "data": data})
        else:
            json_str = json.dumps({"code": 0, "message": msg, "data": data})
        print 111111, msg
        response = urllib2.urlopen(notify_url, json_str, timeout=5)
        print response, "async_lock_ticket"
