# coding:utf-8

import autopay
import time
import sys

def main():
    account = sys.argv[1]
    account_info = {
        "snmpay01": ("snmpaykeyu01", "snmpay001", "keyu_1@qq.com", "keyu86988695", "869886"),
        "snmpay02": ("snmpaykeyu02", "snmpay001", "tianshanhuayuan@qq.com", "keyu86988695", "869886"),
        "snmpay03": ("snmpaykeyu03", "snmpay001", "lvduwanhe@qq.com", "keyu86988695", "869886"),
        #"snmpay02": ("snmpaykeyu02", "snmpay002", "lipigpig@foxmail.com", "luke12308", "300102"),
        #"snmpay03": ("snmpaykeyu03", "snmpay003", "onmyfish@126.com", "luke12308", "300102"),
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

