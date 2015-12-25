# -*- coding:utf-8 -*-
"""
异步锁票任务
"""
import urllib2
import json
import datetime
import time

from datetime import datetime as dte
from app.constants import *
from app import celery
from app.utils import getRedisObj
from app import order_log



@celery.task(ignore_result=True)
def lock_ticket(order_no):
    """
    请求源网站锁票 + 锁票成功回调

    Return:
        expire_time: 122112121,     # 订单过期时间戳
        total_price: 322，          # 车票价格
    """
    from app.models import Order
    order = Order.objects.get(order_no=order_no)
    notify_url = order.locked_return_url
    data = {
        "sys_order_no": order.order_no,
        "out_order_no": order.out_order_no,
        "raw_order_no": order.raw_order_no,
    }
    order_log.info("[lock-start] %s", str(data))
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

        with ScqcpRebot.get_and_lock(order) as rebot:
            ret = rebot.request_lock_ticket(line, riders, contacter)
            if ret["status"] == 1:
                pay_url = "http://www.scqcp.com/ticketOrder/redirectOrder.html?pay_order_id=%s" % ret["pay_order_id"]
                raw_order = "|".join(ret["web_order_id"])
                order.modify(status=STATUS_WAITING_ISSUE,
                             lock_info=ret,
                             lock_datetime=dte.now(),
                             source_account=rebot.telephone,
                             pay_url=pay_url,
                             raw_order_no=raw_order,
                             )
                check_order_expire.apply_async((order.order_no,), countdown=9*60+5)  # 9分钟后执行
                total_price = 0
                for ticket in ret["ticket_list"]:
                    total_price += ticket["server_price"]
                    total_price += ticket["real_price"]
                data.update({
                    "expire_time": ret["expire_time"],
                    "total_price": total_price,
                })

                r = getRedisObj()
                r.zadd('lock_order_list', order.order_no, time.time()*1000)
                json_str = json.dumps({"code": RET_OK, "message": "OK", "data": data})
                order_log.info("[lock-result] succ. order: %s", order.order_no)
            else:
                rebot.remove_doing_order(order)
                order.modify(status=STATUS_LOCK_FAIL,
                             lock_info=ret,
                             lock_datetime=dte.now(),
                             source_account=rebot.telephone)
                json_str = json.dumps({"code": RET_LOCK_FAIL, "message": ret["msg"], "data": data})
                order_log.info("[lock-result] fail. order: %s reason: %s", order.order_no, ret["msg"])
            if notify_url:
                order_log.info("[lock-callback] %s %s", notify_url, json_str)
                response = urllib2.urlopen(notify_url, json_str, timeout=30)
                order_log.info("[lock-callback-response] %s", str(response))

    elif order.crawl_source == "bus100":
        from app.models import Bus100Rebot, Line
        from tasks import check_order_expire
        rebot = Bus100Rebot.get_random_rebot()
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
            flag=order.line.extra_info.get("flag", 0)
            )
        contacter = order.contact_info
        riders = order.riders
        if line['bus_num'] == 0 or not line['flag']:
            ret = {"returnCode": -1, "msg": "该条线路无法购买"}
        else:
            ret = rebot.request_lock_ticket(line, riders, contacter)
        if ret["returnCode"] == "0000" and ret.get('redirectPage', ''):
            expire_time = datetime.datetime.now()+datetime.timedelta(seconds=20*60)
            expire_time = expire_time.strftime("%Y-%m-%d %H:%M:%S")
            ret['expire_time'] = expire_time
            order.modify(status=STATUS_WAITING_ISSUE,
                         lock_info=ret,
                         lock_datetime=dte.now(),
                         pay_url=ret['redirectPage'],
                         raw_order_no=ret['orderNo'],
                         source_account=rebot.telephone)
            check_order_expire.apply_async((order.order_no,), countdown=20*60+5)  # 20分钟后执行
            data.update({
                "expire_time": expire_time,
                "total_price": ret['orderAmt'],
            })
            r = getRedisObj()
            r.zadd('lock_order_list', order.order_no, time.time()*1000)
            json_str = json.dumps({"code": RET_OK, "message": "OK", "data": data})
            order_log.info("[lock-result] succ. order: %s", order.order_no)
        else:
            order.modify(status=STATUS_LOCK_FAIL,
                         lock_info=ret,
                         lock_datetime=dte.now(),
                         source_account=rebot.telephone)
            json_str = json.dumps({"code": RET_LOCK_FAIL, "message": ret.get("msg",'') or ret.get('returnMsg','') , "data": data})
            order_log.info("[lock-result] fail. order:%s reason: %s", order.order_no, ret.get("msg", ""))

        if notify_url:
            order_log.info("[lock-callback] %s %s", notify_url, json_str)
            response = urllib2.urlopen(notify_url, json_str, timeout=30)
            order_log.info("[lock-callback-response] %s", str(response))


@celery.task(ignore_result=True)
def issued_callback(order_no):
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
    from app.models import Order
    order = Order.objects.get(order_no=order_no)
    cb_url = order.issued_return_url
    order_log.info("[issue-callback-start] order:%s, callback:%s", order_no, cb_url)
    if not cb_url:
        return
    if order.status == STATUS_ISSUE_SUCC:
        pick_info = []
        for i, code in enumerate(order.pick_code_list):
            pick_info.append({
                "pick_code": code,
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
    else:
        ret = {
            "code": RET_ISSUED_FAIL,
            "message": "fail",
            "data": {
                "sys_order_no": order.order_no,
                "out_order_no": order.out_order_no,
                "raw_order_no": order.raw_order_no,
            }
        }
    order_log.info("[issue-callback]%s %s", order_no, str(ret))
    response = urllib2.urlopen(cb_url, json.dumps(ret), timeout=10)
    order_log.info("[issue-callback-response]%s %s", order_no, str(response))
