#!/usr/bin/env python
# encoding: utf-8
import csv
import json

from app.constants import *
from app.models import Order
from app import kefu_log

COMPANY_TO_SOURCE = {
    "浙江恒生长运网络科技有限公司": SOURCE_BABA,
    "车巴达(苏州)网络科技有限公司": SOURCE_CBD,
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
        trade_list.append(d)
    return account, trade_list


def match_alipay_order(trade_info):
    """
    根据交易记录匹配订单
    """
    site = trade_info["交易对方"]
    merchant_order = trade_info["商户订单号"]

    crawl_source = COMPANY_TO_SOURCE.get(site, "")
    try:
        return Order.objects.get(crawl_source=crawl_source, raw_order_no=merchant_order)
    except Order.DoesNotExist:
        return None


def import_alipay_record(filename):
    account, trade_list = parse_alipay_record(filename)

    cnt = 0
    for trade_info in trade_list:
        order = match_alipay_order(trade_info)
        if not order:
            kefu_log.error("not found order %s", json.dumps(trade_info, ensure_ascii=False))
            continue
        trade_no = trade_info["交易号"]
        give_back = float(trade_info["成功退款（元）"])
        pay_money = float(trade_info["金额（元）"])
        trade_status = trade_info["交易状态"]

        if order.pay_trade_no and order.pay_trade_no != trade_no:
            kefu_log.error("the order has matched other pay record", json.dumps(trade_info, ensure_ascii=False))
            continue
        if trade_status == "交易关闭":
            if give_back:
                status = PAY_STATUS_REFUND
        elif trade_status == "交易成功":
            status = PAY_STATUS_PAID
        elif trade_status == "退款成功":
            status = PAY_STATUS_REFUND
            give_back = pay_money
            pay_money = order.pay_money
        cnt += 1
        order.modify(pay_trade_no=trade_no,
                    pay_money=pay_money,
                    pay_status=status,
                    pay_channel="alipay",
                    pay_account=account,
                    refund_money=give_back)
    kefu_log.info("update %s record succ.", cnt)
