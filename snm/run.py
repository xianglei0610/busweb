# coding:utf-8

import autopay
import time
import sys

def main():
    account = sys.argv[1]
    account_info = {
        # "snmpay01": ("snmpay01", "snmpay001", "kuo86106@qq.com", "luocky12308", "300l01"),
        # "snmpay01": ("snmpay01", "snmpay001", "lipigpig@foxmail.com", "luocky12308", "300101"),
        "snmpay01": ("snmpay01", "snmpay001", "a13267109876@sohu.com", "xl12308", "b12308"),
        "snmpay02": ("snmpay02", "snmpay002", "lipigpig@foxmail.com", "luocky12308", "300101"),
        "snmpay03": ("snmpay03", "snmpay003", "onmyfish@126.com", "luke12308", "300102"),
        "luojunping2": ("luojunping2", "luocky", "onmyfish@126.com", "luke12308", "300102"),
        # "luojunping2": ("luojunping2", "luocky", "a13267109876@sohu.com", "xll12308", "a12308"),
        "snmpay04": ("snmpay04", "snmpay004", "kuo86106@qq.com", "luke12308", "300l02"),
        "snmpay05": ("snmpay05", "snmpay005", "xianglei0610@163.com", "xl12308", "123081"),
        "snmpay06": ("snmpay06", "snmpay006", "xianglei0610@sina.com", "xll12308", "123081"),
    }
    args = account_info[account]

    driver = autopay.create_driver(*args)
    login_succ = autopay.login_dashboard_api(driver)
    if not login_succ:
        return
    login_succ = autopay.login_dashboard(driver)
    if not login_succ:
        return
    login_succ = autopay.login_alipay(driver)
    if not login_succ:
        return

    while 1:
        reload(autopay)
        orders = autopay.refresh_orders(driver)
        for d in orders:
            autopay.pay(driver, d)

        try:
            autopay.check_alipay_status(driver)
        except Exception, e:
            print e

        time.sleep(1)

if __name__ == "__main__":
    main()

