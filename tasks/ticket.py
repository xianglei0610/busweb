# -*- coding:utf-8 -*-
"""
异步锁票任务
"""
import urllib2
import json
import datetime

from app.constants import *
from app import celery


@celery.task
def lock_ticket(order):
    """
    请求源网站锁票 + 锁票成功回调

    Return:
        expire_time: 122112121,     # 订单过期时间戳
        total_price: 322，          # 车票价格
    """
    notify_url = order.locked_return_url
    if order.crawl_source == "scqcp":
        from app.models import ScqcpRebot
        from tasks import check_order_expire
        line = dict(
            carry_sta_id=order.line.starting.station_id,
            stop_name=order.line.extra_info["stop_name_short"],
            str_date="%s %s" % (order.line.drv_date, order.line.drv_time),
            sign_id=order.line.extra_info["sign_id"],
        )
        contacter = order.contact_info["telephone"]
        riders = order.riders

        with ScqcpRebot.get_and_lock() as rebot:
            ret = rebot.request_lock_ticket(line, riders, contacter)
            data = []
            if ret["status"] == 1:
                pay_url = "http://www.scqcp.com/ticketOrder/redirectOrder.html?pay_order_id=%s" % ret["pay_order_id"]
                order.modify(status=STATUS_LOCK, lock_info=ret, source_account=rebot.telephone, pay_url=pay_url)
                total_price = 0
                for ticket in ret["ticket_list"]:
                    total_price += ticket["server_price"]
                    total_price += ticket["real_price"]
                data = {
                    "expire_time": ret["expire_time"],
                    "total_price": total_price,
                }
                json_str = json.dumps({"code": RET_OK, "message": "OK", "data": data})
            else:
                rebot.remove_doing_order(order)
                order.modify(status=STATUS_LOCK_FAIL, lock_info=ret, source_account=rebot.telephone)
                json_str = json.dumps({"code": 0, "message": ret["msg"], "data": data})
            if notify_url:
                check_order_expire.apply_async((order.order_no,), countdown=8*60+5)  # 8分钟后执行
                response = urllib2.urlopen(notify_url, json_str, timeout=10)
                print response, "async_lock_ticket"

    elif order.crawl_source == "gx84100":
        from app.models import Gx84100Rebot,Line
        rebot = Gx84100Rebot.objects.first()

        ret = rebot.recrawl_shiftid(order.line)
        line = Line.objects.get(line_id=order.line.line_id)
        order.line = line
        order.ticket_price = line.full_price
        order.save()

        line = dict(
            carry_sta_id=order.line.starting.station_id,
            stop_name=order.line.destination.station_name,
            str_date="%s %s" % (order.line.drv_date, order.line.drv_time),
            bus_num=order.line.bus_num,
            flag=order.line.extra_info.get("flag",0)
            )
        contacter = order.contact_info
        riders = order.riders
        if line['bus_num'] ==0 or not line['flag']:
            ret = {"returnCode": -1, "msg": "该条线路无法购买"}
        else:
            ret = rebot.request_lock_ticket(line, riders, contacter)

        data = []
        if ret["returnCode"] == "0000" and ret.get('redirectPage',''):
            expire_time = datetime.datetime.now()+datetime.timedelta(seconds=20*60)
            expire_time = expire_time.strftime("%Y-%m-%d %H:%M:%S")
            ret['expire_time'] = expire_time
            order.modify(status=STATUS_LOCK, lock_info=ret, pay_url=ret['redirectPage'],raw_order_no=ret['orderNo'], source_account=rebot.telephone)

            data = {
                "expire_time": expire_time,
                "total_price": ret['orderAmt'],
            }
            json_str = json.dumps({"code": 1, "message": "OK", "data": data})
        else:
            order.modify(status=STATUS_LOCK_FAIL, lock_info=ret, source_account=rebot.telephone)
            json_str = json.dumps({"code": 0, "message": ret.get("msg",'') or ret.get('returnMsg','') , "data": data})

        if notify_url:
            response = urllib2.urlopen(notify_url, json_str, timeout=10)
            print response, "async_lock_ticket"


@celery.task
def issued_callback(order):
    """
    出票回调

    Return:
    {
        "code": RET_OK,
        "message": "OK"
        "data":{
            "sys_order_no": "",
            "out_order_no": "",
            "raw_order_no"; "",
            "pick_info":[{
                "pick_code": "1",
                "pck_msg": "2"
            },],
        }
    }
    """
    cb_url = order.issued_return_url
    if cb_url:
        pick_info = []
        for i in range(order.pick_code_list):
            pick_info.append({
                "pick_code": order.pick_code_list[i],
                "pick_msg": order.pick_msg_list[i]
                })
        ret = {
            "code": RET_OK,
            "message": "OK",
            "data": {
                "sys_order_no": order.order_no,
                "out_order_no": order.out_order_no,
                "raw_order_no": order.raw_order_no,
                "pick_info": pick_info,
            }
        }
        response = urllib2.urlopen(notify_url, json.dumps(ret), timeout=10)
        print response, "async_issued_callback"
