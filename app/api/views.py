# -*- coding:utf-8 -*-
import json

from datetime import datetime as dte
from app.constants import *
from flask import request, jsonify
from assign import enqueue_wating_lock
from app.api import api
from app.models import Line, Order, OpenCity, OpenStation
from app.flow import get_compatible_flow
from app import order_log, access_log, line_log
from tasks import async_lock_ticket
from app import db


@api.before_request
def log_request():
    access_log.info("[request] %s %s %s", request.environ.get('HTTP_X_REAL_IP', request.remote_addr), request.url, request.get_data())


@api.route('/startings/query', methods=['POST'])
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
    open_citys = OpenCity.objects.filter(is_active=True)
    province_data = {}
    for obj in open_citys:
        province = obj.province
        if province not in province_data:
            province_data[province] = {}
            province_data[province]["province"] = province
            province_data[province]["city_list"] = []

        item = {
            "city_name": obj.city_name,
            "city_code": obj.city_code,
            "is_pre_sell": True,
            "pre_sell_days": obj.pre_sell_days,
            "open_time": obj.open_time,
            "end_time": obj.end_time,
            "advance_order_time": obj.advance_order_time,
            "max_ticket_per_order": obj.max_ticket_per_order,
        }
        province_data[obj.province]["city_list"].append(item)
    return jsonify({"code": RET_OK, "message": "OK", "data": province_data.values()})


@api.route('/destinations/query', methods=['POST'])
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
        starting_name = unicode(post["starting_name"])
        assert starting_name != ""
    except Exception, e:
        return jsonify({"code": RET_PARAM_ERROR, "message": "parameter error", "data": ""})

    try:
        open_city = OpenCity.objects.get(city_name=starting_name, is_active=True)
    except Exception, e:
        return jsonify({"code": RET_CITY_NOT_OPEN, "message": "%s is not open" % starting_name, "data": ""})

    sta_qs = OpenStation.objects.filter(city=open_city)
    if not sta_qs:
        open_city.init_station()
        sta_qs = OpenStation.objects.filter(city=open_city)

    lst = set()
    for sta in sta_qs:
        for d in sta.dest_info:
            lst.add("%s|%s" % (d["name"], d["code"]))
    return jsonify({"code": RET_OK, "message": "OK", "data": list(lst)})


@api.route('/lines/query', methods=['POST'])
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
                "fee": "1",                         # 手续费
                "distance": "11",
            ]
        }
    """
    now = dte.now()
    access_log.info("[query_line] %s" % request.get_data())
    try:
        post = json.loads(request.get_data())
        starting_name = post.get("starting_name")
        dest_name = post.get("destination_name")
        start_date = post.get("start_date")
        assert (starting_name and dest_name and start_date)
        assert now.strftime("%Y-%m-%d") <= start_date
    except:
        return jsonify({"code": RET_PARAM_ERROR, "message": "parameter error", "data": ""})

    try:
        open_city = OpenCity.objects.get(city_name=starting_name)
    except Exception, e:
        return jsonify({"code": RET_CITY_NOT_OPEN, "message": "%s is not open" % starting_name, "data": ""})

    data = []
    for sta in OpenStation.objects.filter(city=open_city):
        if sta.close_status & STATION_CLOSE_BCCX:
            continue
        qs_line = Line.objects.filter(s_city_name__startswith=starting_name,
                                      s_sta_name=sta.sta_name,
                                      d_city_name=dest_name,
                                      drv_date=start_date,
                                      crawl_source=sta.crawl_source)
        data.extend(map(lambda l: l.get_json(), qs_line))
    return jsonify({"code": RET_OK, "message": "OK", "data": data})


@api.route('/lines/detail', methods=['POST'])
def query_line_detail():
    """
    查询线路详细信息， 此接口会从源网站拿最新数据。
    Input:
        {
            "line_id": "1111"          # 线路ID
        }

    """
    req_data = request.get_data()
    line_log.info("[query_line_detail] %s" % req_data)
    post = json.loads(req_data)
    try:
        line = Line.objects.get(line_id=post["line_id"])
    except Line.DoesNotExist:
        return jsonify({"code": RET_LINE_404, "message": "线路不存在", "data": ""})

    open_city = line.get_open_city()
    if open_city and not open_city.is_active:
        return jsonify({"code": RET_CITY_NOT_OPEN, "message": "%s is not open" % open_city.city_name, "data": ""})
    open_station = open_city.get_open_station(line.s_sta_name)
    if not open_station:
        return jsonify({"code": RET_CITY_NOT_OPEN, "message": "%s is not open" % line.s_sta_name, "data": ""})

    if open_station.close_status & STATION_CLOSE_YZCX:
        data = line.get_json()
        data["left_tickets"] = 0
        return jsonify({"code": RET_OK, "message": "%s 余票查询已关闭" % line.s_sta_name, "data": data})
    now_time = dte.now().strftime("%H:%M")
    if now_time >= open_station.end_time  or now_time <= open_station.open_time:
        data = line.get_json()
        data["left_tickets"] = 0
        return jsonify({"code": RET_OK, "message": "售票时间是%s~%s" % (open_station.open_time, open_station.end_time), "data": data})

    flow, new_line = get_compatible_flow(line)
    if not flow:
        data = line.get_json()
        data["left_tickets"] = 0
        return jsonify({"code": RET_OK, "message": "没找到对应flow", "data": data})

    flow.refresh_line(new_line)
    data = new_line.get_json()
    data["line_id"] = line.line_id
    return jsonify({"code": RET_OK, "message": "OK", "data": data})


@api.route('/orders/submit', methods=['POST'])
def submit_order():
    """
    提交订单

    Input:
    {
        "line_id: "2891249051391980105"                     # 线路ID
        "out_order_no": "222"                               # 商户订单号
        "order_price: 11                                    # 订单金额(总票价)
        "contact_info:{                                     # 联系人信息
            "name": "罗军平",                               # 名字
            "telephone": "15575101324",                     # 手机
            "id_type": 1,                                   # 证件类型
            "id_number": "xxxxx",                # 证件号
            "age_level": 1,                                 # 大人 or 小孩
        },
        rider_info: [{                                      # 乘客信息
            "name": "罗军平",                               # 名字
            "telephone": "15575101324",                     # 手机
            "id_type": 1,                                   # 证件类型
            "id_number": "xxxxxx",                # 证件号
            "age_level": 1,                                 # 大人 or 小孩
        }],
        "locked_return_url: ""                    # 锁票成功回调地址
        "issued_return_url: ""                    # 出票成功回调地址
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
    order_log.info("[submit-start] receive order: %s", request.get_data())
    try:
        post = json.loads(request.get_data())
        line_id = post["line_id"]
        contact_info = post["contact_info"]
        rider_list = post["rider_info"]
        out_order_no = post["out_order_no"]
        for info in [contact_info]+rider_list:
            for key in ["name", "telephone", "id_type", "id_number", "age_level"]:
                assert key in info
        order_price = float(post.get("order_price"))
    except:
        order_log.info("[submit-fail] parameter error")
        return jsonify({"code": RET_PARAM_ERROR,
                        "message": "parameter error",
                        "data": ""})

    try:
        line = Line.objects.get(line_id=line_id)
    except Line.DoesNotExist:
        order_log.info("[submit-fail] line not exist")
        return jsonify({"code": RET_LINE_404, "message": "线路不存在", "data": ""})
    flow, line = get_compatible_flow(line)
    if not flow:
        return jsonify({"code": RET_LINE_404, "message": "未找到合适路线", "data": ""})

    try:
        order = Order.objects.get(out_order_no=out_order_no)
        ret = {
            "code": RET_OK,
            "message": u"已存在这个单",
            "data": {"sys_order_no": order.order_no}
        }
        order_log.info("[submit-response] out_order:%s order:%s ret:%s", out_order_no, order.order_no, ret)
        return jsonify(ret)
    except Order.DoesNotExist:
        pass

    ticket_amount = len(rider_list)
    locked_return_url = post.get("locked_return_url", None) or None
    issued_return_url = post.get("issued_return_url", None) or None

    order = Order()
    order.order_no = Order.generate_order_no()
    order.out_order_no = out_order_no
    order.status = STATUS_WAITING_LOCK
    order.order_price = order_price
    order.create_date_time = dte.now()
    order.line = line
    order.ticket_price = line.full_price
    order.ticket_amount = ticket_amount
    order.ticket_fee = line.fee
    order.contact_info = contact_info
    order.riders = rider_list
    order.crawl_source = line.crawl_source
    order.locked_return_url = locked_return_url
    order.issued_return_url = issued_return_url
    order.drv_datetime = line.drv_datetime
    order.bus_num = line.bus_num
    order.starting_name = line.s_city_name + ';' + line.s_sta_name
    order.destination_name = line.d_city_name + ';' + line.d_sta_name
    order.save()
    order.on_create()

    ret = {
        "code": RET_OK,
        "message": "ok",
        "data": {"sys_order_no": order.order_no}
    }
    order_log.info("[submit-response] out_order:%s order:%s ret:%s", out_order_no, order.order_no, ret)
    if order.crawl_source == SOURCE_FB:
        async_lock_ticket.delay(order.order_no)
    else:
        enqueue_wating_lock(order)
    return jsonify(ret)


@api.route('/orders/detail', methods=['POST'])
def query_order_detail():
    """
    订单详情接口

    Input:
        {
            "sys_order_no": "1111"          # 系统订单号
            "out_order_no": "2222"          #12308订单号
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
        data = {}
        post = json.loads(request.get_data())
        sys_order_no = post["sys_order_no"]
        out_order_no = post.get("out_order_no", "")
    except:
        return jsonify({"code": RET_PARAM_ERROR,
                        "message": "parameter error",
                        "data": data})
    try:
        order = Order.objects.get(db.Q(order_no=sys_order_no)|db.Q(out_order_no=out_order_no))
    except Order.DoesNotExist:
        return jsonify({"code": RET_ORDER_404, "message": "order not exist", "data": ""})
    pick_info = []
    if order.status == STATUS_ISSUE_SUCC:
        starting_name_list = order.starting_name.split(';')
        destination_name_list = order.destination_name.split(';')
        drv_datetime_list = dte.strftime(order.drv_datetime, "%Y-%m-%d %H:%M").split(' ')
        for i, code in enumerate(order.pick_code_list):
            pick_info.append({
                "pick_code": code,
                "pick_msg": order.pick_msg_list[i]
            })
        data = {
            "out_order_no": order.out_order_no,
            "raw_order_no": order.raw_order_no,
            "sys_order_no": order.order_no,
            "status": order.status,
            "contacter_info": order.get_contact_info(),
            "rider_info": order.get_rider_info(),
            "need_send_msg": order.need_send_msg,
            "ticket_info": {
                "start_city": starting_name_list[0],
                "start_station": starting_name_list[1],
                "dest_city": destination_name_list[0],
                "dest_station": destination_name_list[1],
                "drv_date": drv_datetime_list[0],
                "drv_time": drv_datetime_list[1],
                "total_price": order.order_price,
            },
            "pick_info": pick_info
        }
        ret = {"code": RET_OK, "message": "OK", "data": data}
    else:
        data = {
            "out_order_no": order.out_order_no,
            "raw_order_no": order.raw_order_no,
            "sys_order_no": order.order_no,
            "status": order.status,
            "contacter_info": {},
            "rider_info": [],
            "ticket_info": {},
            "pick_info": pick_info,
            "need_send_msg": order.need_send_msg,
        }
        ret = {"code": RET_OK, "message": "OK", "data": data}
    access_log.info("[query_order_detail] order:%s out_order_no:%s %s", order.order_no, order.out_order_no, ret)
    return jsonify(ret)

@api.route('/check', methods=['GET'])
def check_status():
    return "working well! %s " % dte.now()
