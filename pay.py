#!/usr/bin/env python
# encoding: utf-8
import csv
import json

from app.constants import *
from app.models import Order
from app import kefu_log, db
from datetime import datetime as dte, timedelta

COMPANY_TO_SOURCE = {
    "浙江恒生长运网络科技有限公司": SOURCE_BABA,
    "车巴达(苏州)网络科技有限公司": SOURCE_CBD,
    "北京巴士壹佰网络科技有限公司": SOURCE_BUS100,
    "上海华程西南国际旅行社有限公司": SOURCE_CTRIP,
    "北京二两科技有限公司": SOURCE_KUAIBA,
    "重庆市公路客运联网售票中心有限公司": SOURCE_CQKY
}

def parse_alipay_record(f):
    """
    交易号 收/支 服务费（元） 最近修改时间 交易来源地 类型 成功退款（元） 金额（元） 商户订单号 商品名称 交易对方 交易状态 付款时间 交易创建时间 备注
    """
    my_decode = lambda i: i.decode("gbk").encode("utf-8")
    account = ""
    trade_list = []
    for i in range(4):
        s = f.next()
        if not s:
            continue
        s = my_decode(s)
        if s.startswith("账号"):
            i, j = s.index("["), s.index("]")
            account = s[i + 1:j]

    for l in csv.DictReader(f):
        d = {}
        for k, v in l.items():
            if v is None:
                break
            d[my_decode(k).strip()]=my_decode(v).strip()
        if not d:
            continue
        trade_list.insert(0, d)
    return account, trade_list


def match_alipay_order(trade_info):
    """
    根据交易记录匹配订单
    """
    site = trade_info["交易对方"]
    merchant_order = trade_info["商户订单号"]
    pay_money = float(trade_info["金额（元）"])
    pay_datetime = dte.strptime(trade_info["交易创建时间"], "%Y-%m-%d %H:%M:%S")
    trade_no = trade_info["交易号"]
    trade_status = trade_info["交易状态"]

    # 通过商户订单号匹配
    crawl_source = COMPANY_TO_SOURCE.get(site, "")
    try:
        order = Order.objects.get(db.Q(pay_order_no=merchant_order)| \
                                  db.Q(raw_order_no=merchant_order),
                                  crawl_source=crawl_source)
    except Order.DoesNotExist:
        order = None

    if not order:
        # 通过金额和下单时间匹配,应该避免走到这一步,因为有可能匹配到多个或者匹配错
        for i in range(1, 10):
            qs = Order.objects.filter(order_price=pay_money,
                                      crawl_source=crawl_source,
                                    lock_datetime__gte=pay_datetime-timedelta(seconds=i*60),
                                    lock_datetime__lte=pay_datetime+timedelta(seconds=i*60))
            qs = qs.filter(db.Q(pay_trade_no="")|db.Q(pay_trade_no=None)|db.Q(pay_trade_no=trade_no))
            qs.order_by("lock_datetime")
            if qs:
                try:
                    has_matched = Order.objects.get(db.Q(pay_trade_no=trade_no)| \
                                                    db.Q(refund_trade_no=trade_no),
                                                    crawl_source=crawl_source)
                except Order.DoesNotExist:
                    has_matched = None
                lst = []
                for i in qs:
                    if has_matched and has_matched.order_no != i.order_no:
                        continue
                    lst.append(i)

                for i in lst:
                    if i.status == 14 and trade_status == "交易成功":
                        order = i
                        break
                    elif i.status in [13, 6] and trade_status == "退款成功":
                        order = i
                        break

                if not order and lst:
                    order = lst[0]
    return order


def import_alipay_record(filename):
    account, trade_list = parse_alipay_record(filename)

    kefu_log.info("支付宝账号:%s", account)
    cnt = 0
    for trade_info in trade_list:
        order = match_alipay_order(trade_info)
        site = trade_info["交易对方"]
        if site == "深圳市一二三零八网络科技有限公司":
            continue
        if not order :
            kefu_log.error("not found order %s", json.dumps(trade_info, ensure_ascii=False))
            continue
        trade_no = trade_info["交易号"]
        give_back = float(trade_info["成功退款（元）"])
        pay_money = float(trade_info["金额（元）"])
        trade_status = trade_info["交易状态"]

        pay_trade_no, refund_trade_no = order.pay_trade_no, order.refund_trade_no
        if trade_status == "退款成功":
            if order.refund_trade_no and order.refund_trade_no != trade_no:
                kefu_log.error("the order has matched other pay record %s", json.dumps(trade_info, ensure_ascii=False))
                continue
            refund_trade_no = trade_no
            status = PAY_STATUS_REFUND
            give_back = pay_money
            pay_money = order.pay_money
        else:
            if order.pay_trade_no and order.pay_trade_no != trade_no:
                kefu_log.error("the order has matched other pay record %s", json.dumps(trade_info, ensure_ascii=False))
                continue

        if trade_status == "交易关闭":
            if give_back:
                status = PAY_STATUS_REFUND
            pay_trade_no = trade_no
        elif trade_status == "交易成功":
            status = PAY_STATUS_PAID
            pay_trade_no = trade_no
        # elif trade_status == "退款成功":
        #     status = PAY_STATUS_REFUND
        #     give_back = pay_money
        #     pay_money = order.pay_money
        cnt += 1
        order.modify(pay_trade_no=pay_trade_no,
                     refund_trade_no=refund_trade_no,
                    pay_money=pay_money,
                    pay_status=status,
                    pay_channel="alipay",
                    pay_account=account,
                    refund_money=give_back)
    kefu_log.info("update %s record succ.", cnt)
