# -*- coding:utf-8 -*-
import urllib2

from app.constants import *
from app.decorators import async


@async
def async_lock_ticket(order):
    """
    请求源网站锁票 + 锁票成功回调

    Return:
        expire_time: 122112121,     # 订单过期时间戳
        total_price: 322，          # 车票价格
    """
    notify_url = order.locked_return_url
    if order.crawl_source == "scqcp":
        from app.models import ScqcpRebot
        rebot = ScqcpRebot.objects.first()
        line = dict(
            carry_sta_id=order.line.starting.station_id,
            stop_name=order.line.destination.station_name,
            str_date="%s %s" % (order.line.drv_date, order.line.drv_time),
            sign_id=order.line.extra_info["sign_id"],
            )
        contacter = order.contact_info["telephone"]
        riders = map(lambda d: {"id_number": d["id_number"], "real_name": str(d["name"])}, order.riders)
        ret = rebot.request_lock_ticket(line, riders, contacter)

        data = []
        if ret["status"] == 1:
            order.updat(status=STATUS_LOCK, lock_info=ret, source_account=rebot.telephone)
            total_price = 0
            for ticket in order.lock_info["ticket_list"]:
                total_price += (ticket["server_price"], ticket["real_price"])
            data = {
                "expire_time": order.lock_info["expire_time"],
                "total_price": total_price,
            }
            json_str = json.dumps({"code": 1, "message": "OK", "data": data})
        else:
            order.updat(status=STATUS_LOCK_FAIL, lock_info=ret, source_account=rebot.telephone)
            json_str = json.dumps({"code": 0, "message": ret["msg"], "data": data})

        if notify_url:
            response = urllib2.urlopen(notify_url, json_str, timeout=10)
            print response, "async_lock_ticket"


@async
def async_issued_callback(order):
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
