# -*- coding:utf-8 -*-
import json

from datetime import datetime
from mongoengine import Q

from app.constants import *
from flask import request, jsonify
from app.async_tasks import async_lock_ticket
from app.main import main
from app.models import Line, Starting, Destination, Order


@main.route('/startings/query', methods=['POST'])
def query_starting():
    """
    出发地查询

    Return:
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
                "max_ticket_per_order": 5,  # 一个订单最多可购买车票的数量
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
            "max_ticket_per_order": obj.max_ticket_per_order,
        }
        province_data[obj.province_name]["city_list"].append(item)
    return jsonify({"code": RET_OK, "message": "OK", "data": province_data.values()})


@main.route('/destinations/query', methods=['POST'])
def query_destination():
    """
    Input:
        {
            "starting_name": "成都",  # 出发地名字
        }

    Return:
        {
            "code": 1,
            "message": "OK",
            "data":[
                "安吉|aj","安平|ap","周庄(江苏昆山)|zz(jsks)"
            ],
        }
    """
    try:
        post = json.loads(request.get_data())
        starting_name = post["starting_name"]
        if not starting_name:
            raise Exception("starting_name is null")
    except:
        return jsonify({"code": RET_PARAM_ERROR,
                        "message": "parameter error",
                        "data": data})

    st_qs = Starting.objects(city_name__startswith=unicode(starting_name))
    dest_list = Destination.objects(starting__in=st_qs)
    data = map(lambda obj: "%s|%s" % (obj.station_name or obj.city_name,
               obj.station_pinyin_prefix or obj.city_pinyin_prefix), dest_list)
    return jsonify({"code": RET_OK, "message": "OK", "data": data})


@main.route('/lines/query', methods=['POST'])
def query_line():
    """
    Input:
    {
        "starting_name":"成都",             # 出发地
        "destination_name": "广州",         # 目的地
        "start_date": "2015-11-11"          # 出发日期,
    }

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
                "full_price": 10,                   # 全价
                "half_price": 5,                    # 半价
                "can_order": 1,                     # 是否可预订
                "fee": "1",                         # 手续费
                "distance": "11",
            ]
        }
    """
    try:
        post = json.loads(request.get_data())
        starting_name = post.get("starting_name" )
        dest_name = post.get("destination_name")
        start_date = post.get("start_date")
        if not (starting_name and dest_name and start_date):
            raise Exception()
    except:
        return jsonify({"code": RET_PARAM_ERROR,
                        "message": "parameter error",
                        "data": data})

    qs_starting = Starting.objects(Q(city_name__startswith=starting_name) |
                                   Q(station_name__startswith=starting_name))
    qs_dest = Destination.objects(Q(city_name__startswith=dest_name) |
                                  Q(station_name__startswith=dest_name))
    qs_line = Line.objects(starting__in=qs_starting,
                           destination__in=qs_dest,
                           drv_date=start_date)

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
            "distance": obj.distance,
        }
    data = map(lambda obj: _extract_data(obj), qs_line)
    return jsonify({"code": RET_OK, "message": "OK", "data": data})


@main.route('/orders/submit', methods=['POST'])
def submit_order():
    """
    提交订单

    Input:
    {
        "line_id: "111"                                     # 线路ID
        "out_order_no": "222"                               # 商户订单号
        "order_price: 11                                    # 订单金额(总票价)
        "contact_info:{                                     # 联系人信息
            "name": "张三",                                 # 名字
            "telephone": "15111111111",                     # 手机
            "id_type": 1,                                   # 证件类型
            "id_number": 421032211990232535,                # 证件号
            "age_level": 1,                                 # 大人 or 小孩
        },
        rider_info: [{                                      # 乘客信息
            "name": "张三",                                 # 名字
            "telephone": "15111111111",                     # 手机
            "id_type": 1,                                   # 证件类型
            "id_number": 421032211990232535,                # 证件号
            "age_level": 1,                                 # 大人 or 小孩
        }],
        "locked_return_url: "http://xxx"                    # 锁票成功回调地址
        "issued_return_url: "http://xxx"                    # 出票成功回调地址
    }

    Return:
        {
           "code": 1,
           "message": "submit order success!"
           "data":{
               "sys_order_no": xxxxxx,
            }
        }
    """
    try:
        post = json.loads(request.get_data())
        line_id = post["line_id"]
        contact_info = post["contact_info"]
        rider_list = post["rider_info"]
        for info in [contact_info]+rider_list:
            for key in ["name", "telephone", "id_type", "id_number", "age_level"]:
                if key not in info:
                    raise Exception("contact or rider lack of %s" % key)
        order_price = float(post.get("order_price"))
    except:
        return jsonify({"code": RET_PARAM_ERROR,
                        "message": "parameter error",
                        "data": data})

    try:
        line = Line.objects.get(line_id=line_id)
    except Line.DoesNotExist:
        return jsonify({"code": RET_LINE_404, "message": "线路不存在", "data": ""})

    ticket_amount = len(rider_list)
    locked_return_url = request.form.get("callback_url", "")
    issued_return_url = request.form.get("issued_return_url", "")

    order = Order()
    order.order_no = Order.generate_order_no()
    order.status = STATUS_COMMIT
    order.order_price = order_price
    order.create_date_time = datetime.now()
    order.line = line
    order.ticket_price = line.full_price
    order.ticket_amount = ticket_amount
    order.ticket_fee = line.fee
    order.contact_info = contact_info
    order.riders = rider_list
    order.crawl_source = line.crawl_source
    order.locked_return_url = locked_return_url
    order.issued_return_url = issued_return_url
    order.save()

    async_lock_ticket(order)
    return jsonify({"code": 1, "message": "submit order success!", "data": {"sys_order_no": order.order_no}})


@main.route('/orders/detail', methods=['POST'])
def query_order_detail():
    """
    订单详情接口

    Input:
        {
            "sys_order_no": "1111"          # 系统订单号
        }


    Return:
        {
            "code": 1,
            "message": "OK",
            "data":{
                "out_order_no": "111",      # 商户订单号
                "raw_order_no": "222",      # 源站订单号
                "sys_order_no": "333",      # 系统订单号
                "status": 14,               # 订单状态
                "rider_info":[{             # 乘客信息
                    "name":"",
                    "telephone": xx,
                    "id_type":1,
                    "id_number": yy,
                    "agen_level": 1,
                }],
                "contacter_info": {
                    "name":"",
                    "telephone": xx,
                    "id_type":1,
                    "id_number": yy,
                    "agen_level": 1,
                }
                "ticket_info": {                # 车票信息
                    "start_city": "",
                    "start_station": "",
                    "dest_city": "",
                    "dest_station": "",
                    "drv_date": "",
                    "drv_time": "",
                    "total_price": "",
                }
             }
        }
    """
    try:
        post = json.loads(request.get_data())
        sys_order_no = post["sys_order_no"]
    except:
        return jsonify({"code": RET_PARAM_ERROR,
                        "message": "parameter error",
                        "data": data})
    try:
        order = Order.objects.get(order_no=sys_order_no)
    except Order.DoesNotExist:
        return jsonify({"code": RET_ORDER_404, "message": "order not exist", "data": ""})

    if order.status == STATUS_SUCC:
        data = {
            "out_order_no": order.out_order_no,
            "raw_order_no": order.raw_order_no,
            "sys_order_no": order.sys_order_no,
            "status": order.status,
            "contacter_info": order.get_contact_info(),
            "rider_info": order.get_rider_info(),
            "ticket_info": {
                "start_city": order.line.starting.city_name,
                "start_station": order.line.starting.station_name,
                "dest_city": order.line.destination.city_name,
                "dest_station": order.line.destination.station_name,
                "drv_date": order.line.drv_date,
                "drv_time": order.line.drv_time,
                "total_price": order.order_price,
            }
        }
        return jsonify({"code": RET_OK, "message": "OK", "data": data})
    else:
        data = {
            "out_order_no": order.out_order_no,
            "raw_order_no": order.raw_order_no,
            "sys_order_no": order.sys_order_no,
            "status": order.status,
            "contacter_info": {},
            "rider_info": [],
            "ticket_info": {},
        }
        return jsonify({"code": RET_OK, "message": "OK", "data": data})


@main.route('/orders/refresh', methods=['POST'])
def refresh_order():
    """
    刷新订单状态

    Input:
        {
            "sys_order_no": "1111"   # 订单号
        }

    Return:
    {
        "status": 14,
    }
    """
    try:
        post = json.loads(request.get_data())
        sys_order_no = post["sys_order_no"]
    except:
        return jsonify({"code": RET_PARAM_ERROR,
                        "message": "parameter error",
                        "data": data})
    try:
        order = Order.objects.get(order_no=sys_order_no)
    except Order.DoesNotExist:
        return jsonify({"code": RET_ORDER_404, "message": "order not exist", "data": ""})
    order.refresh_status()
    return jsonify({"code": RET_OK, "message": "refresh success", "data": {"status": order.status}})
