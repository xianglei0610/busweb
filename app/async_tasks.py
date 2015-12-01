# -*- coding:utf-8 -*-
import urllib2

from app.constants import *
from app.models import ScqcpRebot


def async_lock_ticket(order):
    """
    请求源网站锁票

    Return:
        expire_time: 122112121,     # 订单过期时间戳
        total_price: 322，          # 车票价格
    """
    notify_url = order.locked_return_url
    if order.crawl_source == "scqcp":
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
            response = urllib2.urlopen(notify_url, json_str, timeout=5)
            print response, "async_lock_ticket"
