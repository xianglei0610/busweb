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
    "重庆市公路客运联网售票中心有限公司": SOURCE_CQKY,
    "同程国际旅行社有限公司": SOURCE_TC,
    "苏州创旅天下信息技术有限公司": SOURCE_TC,
    "四川倍施特科技股份有限公司": SOURCE_SCQCP,
    "江苏长运交通科技有限公司": SOURCE_JSKY,
    "苏州世纪飞越网络信息有限公司": SOURCE_WXSZ,
    "苏州汽车客运集团有限公司汽车客运总站": SOURCE_ZJGSM,
    "南京市道路客运联网售票管理服务中心": SOURCE_JSDLKY,
    "南京趣普电子商务有限公司": SOURCE_CHANGTU,
    "南京晨之义软件科技有限公司": lambda name: SOURCE_NMGHY if u"内蒙古网站售票" in name else SOURCE_TZKY,
    "北京盛威时代科技有限公司": SOURCE_BUS365,
    "辽宁新途网络科技有限公司": SOURCE_XINTUYUN,
    "河南金象客运信息服务有限公司": SOURCE_HN96520,
    "广东南粤通客运联网中心有限公司": SOURCE_GDSW,
    "徐州公路运输集团有限责任公司": SOURCE_XYJT,
    "东莞市汇联票务服务有限公司": SOURCE_DGKY,
    "北京阿尔萨客运有限公司": SOURCE_E8S,
    "烟台远征电子科技开发有限公司": SOURCE_SD365,
    "上海天雅物联网科技有限公司": SOURCE_LVTU100,
    "安徽恒生皖美网络科技有限公司": SOURCE_WMCX,
    "贵州大迈科技有限公司": SOURCE_GZQCP,
    "上海长途汽车客运总站有限公司": SOURCE_SHKYZZ,
    "广州浩宁智能设备有限公司": SOURCE_ZUOCHE,
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
    name= trade_info["商品名称"]
    crawl_source = COMPANY_TO_SOURCE.get(site, "")

    # 通过商户订单号匹配
    if callable(crawl_source):
        crawl_source = crawl_source(name)
    try:
        order = Order.objects.get(db.Q(pay_order_no=merchant_order)| \
                                  db.Q(raw_order_no=merchant_order),
                                  crawl_source=crawl_source)
    except Order.DoesNotExist:
        order = None

    if not order and crawl_source == "zuoche":
        name = name.lstrip("退款-")
        name_split = name.split(" ")
        for i in range(1, 3):
            # "商品名称": "2016-09-30 12:00:00 广州汽车客运站-惠东城南汽车客运站，3 张。"
            drv_datetime = dte.strptime("%s %s" % (name_split[0], name_split[1]),"%Y-%m-%d %H:%M:%S")
            ticket_amount = int(name_split[2].split("，")[1].strip())
            s_sta_name, d_sta_name = name_split[2].split("，")[0].split("-")[0], name_split[2].split("，")[0].split("-")[1]
            s_sta_name, d_sta_name = unicode(s_sta_name), unicode(d_sta_name)

            qs = Order.objects.filter(ticket_amount=ticket_amount,
                                      drv_datetime=drv_datetime,
                                      crawl_source=crawl_source,
                                      starting_name__endswith=s_sta_name,
                                      destination_name__endswith=d_sta_name,
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
    kefu_log.info("文件名:%s", filename.name)
    account, trade_list = parse_alipay_record(filename)
    kefu_log.info("支付宝账号:%s", account)

    cnt = 0
    for trade_info in trade_list:
        order = match_alipay_order(trade_info)
        site = trade_info["交易对方"]
        trade_status = trade_info["交易状态"]
        if site in ["深圳市一二三零八网络科技有限公司", "深圳市哈巴科技有限公司(*圳市哈巴科技有限公司)", "深圳市哈巴科技有限公司", "天弘基金管理有限公司"]:
            continue
        if not order:
            if trade_status not in ["交易关闭", "等待付款"]:
                kefu_log.info("not found order %s", json.dumps(trade_info, ensure_ascii=False))
            continue
        trade_no = trade_info["交易号"]
        give_back = float(trade_info["成功退款（元）"])
        pay_money = float(trade_info["金额（元）"])

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
            else:
                status = PAY_STATUS_UNPAID
            pay_trade_no = trade_no
        elif trade_status == "等待付款":
            status = PAY_STATUS_UNPAID
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
