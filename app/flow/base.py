# -*- coding:utf-8 -*-
import urllib2
import json
import traceback
import os
import time

from app.constants import *
from app import order_log, line_log
from datetime import timedelta, datetime as dte
from tasks import issued_callback
from bs4 import BeautifulSoup
from app.utils import get_redis


class Flow(object):
    name = "flow"

    def check_lock_condition(self, order):
        if order.status not in [STATUS_LOCK_RETRY, STATUS_WAITING_LOCK]:
            return "%s状态不允许再发起锁票" % STATUS_MSG[order.status]
        return ""

    def lock_ticket(self, order, **kwargs):
        """
        锁票主流程, 子类不用复写此方法
        """
        rds = get_redis("order")
        key = RK_ORDER_LOCKING % order.order_no
        if rds.get(key):
            return
        rds.set(key, time.time())
        rds.expire(key, 120)
        try:
            ret = self.lock_ticket2(order, **kwargs)
            return ret
        finally:
            rds.delete(key)

    def lock_ticket2(self, order, **kwargs):
        order.reload()
        notify_url = order.locked_return_url
        data = {
            "sys_order_no": order.order_no,
            "out_order_no": order.out_order_no,
            "raw_order_no": order.raw_order_no,
        }
        call_from = traceback.format_stack()[-2]
        order_log.info("[lock-start] order: %s call from: %s", order.order_no, call_from.replace(os.linesep, " "))
        fail_msg = self.check_lock_condition(order)
        if fail_msg:  # 防止重复下单
            order_log.info("[lock-fail] order: %s %s", order.order_no, fail_msg)
            return

        ret = self.do_lock_ticket(order, **kwargs)
        order.reload()
        fail_msg = self.check_lock_condition(order)
        if fail_msg:  # 再次检查, 防止重复支付
            order_log.info("[lock-ignore] order: %s %s", order.order_no, fail_msg)
            return

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
            order.reload()

            data.update({
                "raw_order_no": order.raw_order_no,
                "expire_time": ret["expire_datetime"].strftime("%Y-%m-%d %H:%M:%S"),
                "total_price": order.order_price,
            })
            json_str = json.dumps({"code": RET_OK, "message": "OK", "data": data})
            order_log.info("[lock-result] succ. order: %s source_account:%s", order.order_no, order.source_account)
        elif ret["result_code"] == 2:   # 锁票失败,进入锁票重试
            order.modify(source_account=ret["source_account"], lock_info=ret["lock_info"])
            self.lock_ticket_retry(order)
            order_log.info("[lock-result] retry. order: %s, reason: %s", order.order_no, ret["result_reason"])
            return
        elif ret["result_code"] == 0:   # 锁票失败
            order.modify(status=STATUS_LOCK_FAIL,
                         lock_info=ret["lock_info"],
                         lock_datetime=dte.now(),
                         source_account=ret["source_account"])
            order.on_lock_fail()
            json_str = json.dumps({"code": RET_LOCK_FAIL, "message": ret["result_reason"], "data": data})
            order_log.info("[lock-result] fail. order: %s, reason: %s", order.order_no, ret["result_reason"])
        elif ret["result_code"] == 3:   # 锁票输验证码
            order_log.info("[lock-result] order:%s need valid code", order.order_no)
            return
        else:
            order_log.info("[lock-result] unrecognize. order: %s, reason: %s code:%s", order.order_no, ret["result_reason"], ret["result_code"])
            return

        if notify_url:
            order_log.info("[lock-callback] order:%s, %s %s", order.order_no, notify_url, json_str)
            response = urllib2.urlopen(notify_url, json_str, timeout=20)
            order_log.info("[lock-callback-response] order:%s, %s", order.order_no, response.read())

    def do_lock_ticket(self, order, **kwargs):
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

    def need_refresh_issue(self, order, force=False):
        """
        是否有必要刷新出票
        """
        if force:
            return True
        if order.status not in (STATUS_ISSUE_ING, STATUS_WAITING_ISSUE):
            return False
        return True

    def refresh_issue(self, order, force=False):
        """
        出票刷新主流程，子类不用重写
        """
        old_status = order.status
        if not self.need_refresh_issue(order, force=force):
            return
        order_log.info("[issue-refresh-start] order:%s", order.order_no)
        ret = self.do_refresh_issue(order)
        order.reload()
        code = ret["result_code"]

        code_status_mapping = {
            0: old_status,
            1: STATUS_ISSUE_SUCC,
            2: STATUS_ISSUE_FAIL,
            3: STATUS_GIVE_BACK,
            4: STATUS_ISSUE_ING,
        }
        if code_status_mapping.get(code, "") == old_status:
            return
        if code == 0:
            return
        elif code == 1:         # 出票成功
            msg_list = ret["pick_msg_list"] or order.pick_msg_list
            msg = msg_list and msg_list[0] or ""
            order_log.info("[issue-refresh-result] order: %s succ. msg:%s, pick_msg: %s",
                            order.order_no,
                            ret["result_msg"],
                            msg)
            order.modify(status=STATUS_ISSUE_SUCC,
                         pick_code_list=ret["pick_code_list"] or order.pick_code_list,
                         pick_msg_list=msg_list)
            order.on_issue_success()
            issued_callback.delay(order.order_no)
        elif code == 2:         # 出票失败
            order_log.info("[issue-refresh-result] order: %s fail. msg:%s", order.order_no, ret["result_msg"])
            order.modify(status=STATUS_ISSUE_FAIL)
            order.on_issue_fail(ret["result_msg"])
            issued_callback.delay(order.order_no)
        elif code == 3:         # 源站已退款
            order_log.info("[issue-refresh-result] order: %s give back. msg:%s", order.order_no, ret["result_msg"])
            order.modify(status=STATUS_GIVE_BACK)
            issued_callback.delay(order.order_no)
            order.on_give_back()
        elif code == 4:         # 正在出票
            order_log.info("[issue-refresh-result] order: %s issueing. msg:%s", order.order_no, ret["result_msg"])
            order.modify(status=STATUS_ISSUE_ING)
            order.on_issueing()
        elif code == 5:         # 超时过期, 进入锁票重试
            order_log.info("[issue-refresh-result] order: %s expire. msg:%s", order.order_no, ret["result_msg"])
            order.modify(pay_order_no="", raw_order_no="", lock_info={})
            self.lock_ticket_retry(order)
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

    def need_refresh_line(self, line, force=False):
        """
        检查线路是否需要刷新, 用来控制不要太过于频繁刷新
        """
        if force:    # 强制刷新
            return True
        if not line.refresh_datetime:   # 从没刷新过，刷新
            return True
        now = dte.now()
        last_refresh = (now-line.refresh_datetime).total_seconds()
        if line.left_tickets<=0:    # 余票为0， 不刷新
            return False
        elif line.left_tickets<10 and last_refresh < 60:    # 20s之前刷新过了，不刷新
            return False
        elif last_refresh < 5*60:
            return False
        return True

    def valid_line(self, line):
        now = dte.now()
        # 预售提前时间
        if line.s_province == "四川":
            adv_minus = 140
        else:
            adv_minus = 30

        if (line.drv_datetime-now).total_seconds() <= adv_minus*60:
            return False

        # 不能买第二天太早的票
        h = now.hour
        limit_datetime = None
        if h==23:
            limit_datetime = dte.strptime((now+timedelta(days=1)).strftime("%Y-%m-%d")+" 07:30", "%Y-%m-%d %H:%M")
        elif 0<=h<7:
            limit_datetime = dte.strptime(now.strftime("%Y-%m-%d")+" 07:30", "%Y-%m-%d %H:%M")
        if limit_datetime and line.drv_datetime < limit_datetime+timedelta(minutes=adv_minus):
            return False
        return True

    def refresh_line(self, line, force=False):
        """
        线路信息刷新主流程, 不用子类重写
        """
        line_log.info("[refresh-start] line:%s %s, left_tickets:%s ", line.crawl_source, line.line_id, line.left_tickets)
        if not self.valid_line(line):
            line.modify(left_tickets=0, refresh_datetime=dte.now())
            line_log.info("[refresh-result] line:%s %s, invalid line", line.crawl_source, line.line_id)
            return
        if not self.need_refresh_line(line, force=force):
            line_log.info("[refresh-result] line:%s %s, not need refresh", line.crawl_source, line.line_id)
            return
        ret = self.do_refresh_line(line)
        update = ret["update_attrs"]
        now = dte.now()
        if update:
            if "refresh_datetime" not in update:
                update["refresh_datetime"] = now
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
            "update_attrs":{    # 要修改的Document属性
                "left_tickets": 1,
                "fee": 0,
                ....
                ....
            }
        }
        """
        raise Exception("Not Implemented")

    def close_line(self, line, reason=""):
        """
        关闭线路
        """
        if not line:
            return
        line_log.info("[close] line:%s %s, reason:%s", line.crawl_source, line.line_id, reason)
        now = dte.now()
        line.modify(left_tickets=0, update_datetime=now, refresh_datetime=now)

    def lock_ticket_retry(self, order):
        order.modify(status=STATUS_LOCK_RETRY)
        order.on_lock_retry()

    def extract_alipay(self, content):
        """
        Input:
        <form name="alipaysubmit" method="post" action="https://mapi.alipay.com/gateway.do?_input_charset=utf-8">
            <input type=hidden name="body" value="&#23458;&#36816;&#27773;&#36710;&#31080;&#65288;&#35746;&#21333;&#32534;&#21495;&#65306;1600281634&#65289;">
            <input type=hidden name="notify_url" value="http://www.bababus.com/bankresults/payresultalin.htm">
            <input type=hidden name="out_trade_no" value="1600281634">
            <input type=hidden name="partner" value="2088121049160648">
            <input type=hidden name="payment_type" value="1">
            <input type=hidden name="seller_email" value="bababus@bababus.com">
            <input type=hidden name="service" value="create_direct_pay_by_user">
            <input type=hidden name="sign" value="211d37eb1941429942ecee90bfcb789e">
            <input type=hidden name="sign_type" value="MD5">
            <input type=hidden name="subject" value="&#23458;&#36816;&#27773;&#36710;&#31080;">
            <input type=hidden name="total_fee" value="11">
            <input type=hidden name="show_url" value="http://keyun.96520.com.cn/">
            <input type=hidden name="return_url" value="http://www.bababus.com/bankresults/payresultali.htm">
            <input type=hidden name="it_b_pay" value="20m">
            </form>
        <script language="JavaScript">
            document.alipaysubmit.submit();
        </script>

        Output:
        {
            "body": "客运汽车票（订单编号：1600281634）",
            "seller_email": "bababus@bababus.com",
            "total_fee": "11",
            "service": "create_direct_pay_by_user",
            "show_url": "http://keyun.96520.com.cn/",
            "sign": "211d37eb1941429942ecee90bfcb789e",
            "out_trade_no": "1600281634",
            "payment_type": "1",
            "notify_url": "http://www.bababus.com/bankresults/payresultalin.htm",
            "sign_type": "MD5",
            "partner": "2088121049160648",
            "it_b_pay": "20m",
            "return_url": "http://www.bababus.com/bankresults/payresultali.htm",
            "subject": "客运汽车票"
        }
        """
        soup = BeautifulSoup(content, "lxml")
        data = {}
        for e in soup.findAll("input"):
            data[e.get("name")] = e.get("value")
        return data
