# -*- coding:utf-8 -*-
import urllib2
import json

from app.constants import *
from app import order_log, line_log
from datetime import datetime as dte
from tasks import check_order_expire, issued_callback, refresh_issueing_order


class Flow(object):
    name = "flow"

    def lock_ticket(self, order):
        """
        锁票主流程, 子类不用复写此方法

        Return:
            expire_time: "2015-11-11 11:11:11",     # 订单过期时间
            total_price: 322，          # 车票价格
        """
        notify_url = order.locked_return_url
        data = {
            "sys_order_no": order.order_no,
            "out_order_no": order.out_order_no,
            "raw_order_no": order.raw_order_no,
        }
        order_log.info("[lock-start] order: %s", order.order_no)
        ret = self.do_lock_ticket(order)
        now = dte.now()
        if ret["result_code"] == 1:   # 锁票成功
            order.modify(status=STATUS_WAITING_ISSUE,
                         lock_info=ret["lock_info"],
                         lock_datetime=dte.now(),
                         source_account=ret["source_account"],
                         pay_url=ret["pay_url"],
                         raw_order_no=ret["raw_order_no"],
                         pay_money=ret["pay_money"],
                         )
            order.on_lock_success()
            seconds_left = max(0, (ret["expire_datetime"]-now).total_seconds())
            check_order_expire.apply_async((order.order_no,), countdown=seconds_left+5)

            data.update({
                "raw_order_no": order.raw_order_no,
                "expire_time": ret["expire_datetime"].strftime("%Y-%m-%d %H:%M:%S"),
                "total_price": order.order_price,
            })
            json_str = json.dumps({"code": RET_OK, "message": "OK", "data": data})
            order_log.info("[lock-result] succ. order: %s", order.order_no)
        elif ret["result_code"] == 2:   # 锁票失败,进入锁票重试
            order.modify(source_account=ret["source_account"])
            self.lock_ticket_retry(order)
            order_log.info("[lock-result] retry. order: %s, reason: %s", order.order_no, ret["result_reason"])
            return
        else:   # 锁票失败
            order.modify(status=STATUS_LOCK_FAIL,
                         lock_info=ret["lock_info"],
                         lock_datetime=dte.now(),
                         source_account=ret["source_account"])
            order.on_lock_fail()
            json_str = json.dumps({"code": RET_LOCK_FAIL, "message": ret["result_reason"], "data": data})
            order_log.info("[lock-result] fail. order: %s, reason: %s", order.order_no, ret["result_reason"])

        if notify_url:
            order_log.info("[lock-callback] order:%s, %s %s", order.order_no, notify_url, json_str)
            response = urllib2.urlopen(notify_url, json_str, timeout=20)
            order_log.info("[lock-callback-response] order:%s, %s", order.order_no, str(response))

    def do_lock_ticket(self, order):
        """
        实际锁票动作, 需要子类实现
        Returns:
        {
            "lock_info": {},
            "result_code": 0,       # 0-失败， 1-成功
            "result_reason": "",    # 失败原因
            "pay_url": "",          # 支付链接
            "raw_order_no":""       # 源站订单号
            "source_account":""     # 源站账号
            "expire_datetime": ""   # 锁票过期时间
            "pay_money": 0.0,       # 源站要求支付多少
        }
        """
        raise Exception("Not Implemented")

    def need_refresh_issue(self, order):
        """
        是否有必要刷新出票
        """
        if order.status not in (STATUS_ISSUE_ING, STATUS_WAITING_ISSUE):
            return False
        return True

    def refresh_issue(self, order):
        """
        出票刷新主流程，子类不用重写
        """
        old_status = order.status
#         if not self.need_refresh_issue(order):
#             return
        order_log.info("[issue-refresh-start] order:%s", order.order_no)
        ret = self.do_refresh_issue(order)
        code = ret["result_code"]

        code_status_mapping = {
            0: old_status,
            1: STATUS_ISSUE_SUCC,
            2: STATUS_ISSUE_FAIL,
            3: STATUS_GIVE_BACK,
            4: STATUS_ISSUE_ING,
        }
        if code_status_mapping.get(code, None) == old_status:
            return
        if code == 0:
            return
        elif code == 1:
            order_log.info("[issue-refresh-result] order: %s succ. msg:%s, pick_msg: %s",
                            order.order_no,
                            ret["result_msg"],
                            str(ret["pick_msg_list"]))
            order.modify(
                    status=STATUS_ISSUE_SUCC,
                    pick_code_list=ret["pick_code_list"],
                    pick_msg_list=ret["pick_msg_list"])
            order.on_issue_success()
            issued_callback.delay(order.order_no)
        elif code == 2:
            order_log.info("[issue-refresh-result] order: %s fail. msg:%s", order.order_no, ret["result_msg"])
            order.modify(status=STATUS_ISSUE_FAIL)
            order.on_issue_fail(ret["result_msg"])
            issued_callback.delay(order.order_no)
        elif code == 3:
            order_log.info("[issue-refresh-result] order: %s give back. msg:%s", order.order_no, ret["result_msg"])
            order.modify(status=STATUS_GIVE_BACK)
            issued_callback.delay(order.order_no)
            order.on_give_back()
        elif code == 4:
            order_log.info("[issue-refresh-result] order: %s issueing. msg:%s", order.order_no, ret["result_msg"])
            order.modify(status=STATUS_ISSUE_ING)
            refresh_issueing_order.delay(order.order_no)
            order.on_issueing()
        else:
            order_log.error("[issue-refresh-result] order: %s error, 未处理状态 status:%s", order.order_no, code)

    def do_refresh_issue(self, order):
        """
        刷新出票, 子类需要各自实现
        Returns:
        {
            "result_code": 0,      #订单状态 0-状态未改变 1-出票成功 2-出票失败 3-已退票 4-正在出票
            "result_msg": "",
            "pick_code_list": [],   #取票号
            "pick_msg_list": [], ,  #取票短信
        }
        """
        raise Exception("Not Implemented")

    def is_need_refresh(self, line, force=False):
        """
        检查线路是否需要刷新, 用来控制不要太过于频繁刷新
        """
        if force:    # 强制刷新
            return True
        if not line.refresh_datetime:   # 从没刷新过，刷新
            return True
        now = dte.now()
        last_refresh = (now-line.refresh_datetime).total_seconds()
        if last_refresh<15:    # 15s之前刷新过了，不刷新
            return False
        elif last_refresh < 2*60*60 and line.left_tickets<=0:    # 2小时之内刷新过，但上次刷新已经没票了。此次不刷新
            return False
        return True

    def refresh_line(self, line, force=False):
        """
        线路信息刷新主流程, 不用子类重写
        """
        line_log.info("[refresh-start] line:%s %s, left_tickets:%s ", line.crawl_source, line.line_id, line.left_tickets)
        if not self.is_need_refresh(line, force=force):
            line_log.info("[refresh-result] line:%s %s, not need refresh", line.crawl_source, line.line_id)
            return
        ret = self.do_refresh_line(line)
        update = ret["update_attrs"]
        if update:
            line.modify(**update)
        line_log.info("[refresh-result] line:%s %s, result: %s, update: %s",
                      line.crawl_source,
                      line.line_id,
                      ret["result_msg"],
                      str(update))


    def do_refresh_line(self, line):
        """
        线路信息刷新, 各子类单独实现

        Returns:
        {
            "result_msg": "",
            "update_attrs":{    # 要修改的model属性
                "left_tickets": 1,
                "fee": 0,
                ....
                ....
            }
        }
        """
        raise Exception("Not Implemented")

    def lock_ticket_retry(self, order):
        order.modify(status=STATUS_LOCK_RETRY)
        order.on_lock_retry()