# coding:utf-8
import requests
import sys
import time
import os
reload(sys)
sys.setdefaultencoding("utf-8")

from datetime import datetime as dte
from selenium import webdriver
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.common.by import By
from selenium.common.exceptions import NoSuchElementException, UnexpectedAlertPresentException
from selenium.webdriver.common.keys import Keys

#DASHBOARD_URL = "http://localhost:8200"
DASHBOARD_URL = "http://d.12308.com"


def create_driver(dashboard_account, dashboard_password, alipay_account, alipay_password, alipay_paypwd):
    pf = os.sys.platform
    if "win32" in pf:  # windows
        iedriver = "D:\drivers\IEDriverServer.exe"
        chromedriver= "D:\drivers\chromedriver.exe"
        os.environ["webdriver.ie.driver"] = iedriver
        os.environ["webdriver.chrome.driver"] = chromedriver
        driver = webdriver.Ie(iedriver)
    elif "linux" in pf: # linux
        driver = webdriver.Chrome(executable_path="./chromedriver_linux")
    else:       # macos
        driver = webdriver.Chrome(executable_path="./chromedriver")
        # driver = webdriver.Firefox()
    # page timeout
    driver.set_page_load_timeout(30)

    driver.dashboard_account = dashboard_account
    driver.dashboard_password = dashboard_password
    driver.alipay_account = alipay_account
    driver.alipay_password = alipay_password
    driver.alipay_paypwd = alipay_paypwd
    driver.paypwd_type = {}
    driver.payed_orders = {}
    driver.try_pay_times = {}   # 尝试支付次数
    driver.alipay_online = True
    return driver

def login_alipay(driver):
    account, pwd = driver.alipay_account, driver.alipay_password
    print "正在登陆支付宝..."
    driver.get("https://auth.alipay.com/login/index.htm")

    # 账号
    el_name= WebDriverWait(driver, 10).until(EC.presence_of_element_located((By.ID, "J-input-user")))
    el_name.send_keys(account)
    el_btn = WebDriverWait(driver, 10).until(EC.element_to_be_clickable((By.ID, "J-login-btn")))

    # 密码
    try:
        el_pwd = WebDriverWait(driver, 5).until(EC.visibility_of_element_located((By.ID, "password_rsainput")))
    except:
        el_pwd = driver.find_element_by_id("password_input")
    el_pwd.clear()
    el_pwd.send_keys(pwd)

    # 验证码
    try:
        el_code = driver.find_element_by_id("J-input-checkcode")
        while 1:
            el_code.clear()
            el_code.send_keys(raw_input("请输入验证码:"))
            time.sleep(2)
            if driver.find_element_by_xpath("//span[@id='J-checkcodeIcon']/i").get_attribute("title") == "成功":
                break
    except:
        pass
    el_btn.click()

    time.sleep(3)
    # 短信验证码
    if "checkSecurity" in driver.current_url:
        driver.execute_script("document.getElementById('riskackcode').value='%s';" % raw_input("请输入6位短信验证码："))
        driver.find_element_by_css_selector("#J-submit input").click()

    try:
        time.sleep(3)
        if "uemprod" in driver.current_url:
            email = driver.find_element_by_id("J_logonId").get_attribute("value")
        else:
            email = driver.find_element_by_id("J-userInfo-account-userEmail").text
        print "登陆成功", email
        return True
    except Exception, e:
        print "登陆失败!", e
        return False


def login_dashboard(driver):
    print "正在登陆dashboard..."
    account, pwd = driver.dashboard_account, driver.dashboard_password
    driver.get(DASHBOARD_URL + "/login")

    # 账号
    el_name= WebDriverWait(driver, 10).until(EC.presence_of_element_located((By.ID, "user")))
    el_name.send_keys(account)

    # 密码
    el_pwd = WebDriverWait(driver, 5).until(EC.presence_of_element_located((By.ID, "password")))
    el_pwd.send_keys(pwd)

    # 验证码
    if "snmpay" not in account:
        el_code = driver.find_element_by_id("code")
        el_code.clear()
        el_code.send_keys(raw_input("请输入验证码:"))

    # button click
    el_btn = WebDriverWait(driver, 10).until(EC.element_to_be_clickable((By.TAG_NAME, "button")))
    el_btn.click()
    if driver.current_url.endswith(u"/orders/my"):
        print "登陆dashboard成功"
        return True
    print "登陆dashboard失败"
    return False


def login_dashboard_api(driver):
    print "正在登陆dashboard api..."
    account, pwd = driver.dashboard_account, driver.dashboard_password
    r = requests.post(DASHBOARD_URL+"/login?type=api", data={"username": account, "password": pwd})
    res = r.json()
    if res["code"] == 1:
        print "登陆dashboard api成功"
        driver.dashboard_token = res["token"]
        return True
    print "登陆dashboard api失败"
    return False


def refresh_orders(driver):
    if not driver.alipay_online:
        print "支付宝不在线，不刷新订单"
        return []
    try:
        r = requests.get(DASHBOARD_URL+"/orders/dealing?type=api", headers={"token": driver.dashboard_token}, timeout=30)
        res = r.json()
    except Exception, e:
        print "refresh_orders:", e
        return []
    return res["orders"]


def give_to_other(driver, order_info, reason=""):
    "把单转给其他人"
    data = {"content": "selenium: "+reason}
    try:
        r = requests.post(DASHBOARD_URL+"/orders/"+order_info["order_no"]+"/addremark", data=data, headers={"token": driver.dashboard_token})
        data = {"pk": order_info["order_no"], "value": "luojunping"}
        r = requests.post(DASHBOARD_URL+"/orders/changekefu", data=data, headers={"token": driver.dashboard_token})
        res = r.json()
        if res["code"] == 1:
            return True
        return False
    except Exception, e:
        print e
        return False

def pay_pc(driver, order_info):
    source = order_info["crawl_source"]
    try_id1 = driver.paypwd_type.get(source, "payPassword_rsainput")
    try_id2 = "payPassword_input" if try_id1 == "payPassword_rsainput" else "payPassword_rsainput"
    try:
        el_pwd = WebDriverWait(driver, 1).until(EC.presence_of_element_located((By.ID, try_id1)))
        driver.paypwd_type[source] = try_id1
    except:
        el_pwd = WebDriverWait(driver, 5).until(EC.presence_of_element_located((By.ID, try_id2)))
        driver.paypwd_type[source] = try_id2

    el_pwd.clear()
    el_pwd.send_keys(driver.alipay_paypwd)
    el_btn = WebDriverWait(driver, 5).until(EC.element_to_be_clickable((By.ID, "J_authSubmit")))
    el_btn.click()

    # 是否支付成功判断
    def _check_succ(driver):
        t = 0
        while 1:
            t += 1
            if u"result/waitResult" in driver.current_url:
                driver.payed_orders[order_info["order_no"]] = time.time()
                return True
            time.sleep(1)
            if t>5:
                return False

    if not _check_succ(driver):
        frames = driver.find_elements_by_tag_name("iframe")
        if len(frames) >1:  # 有弹框
            # import pdb; pdb.set_trace()
            driver.switch_to_frame(frames[1])
            try:
                el_code = driver.find_element_by_id("ackcode")
            except:
                el_code = driver.find_element_by_id("riskackcode")
            while 1:
                el_code.clear()
                el_code.send_keys(raw_input("请输入短信验证码:"))
                driver.find_element_by_css_selector("#J_authSubmit").click()
                time.sleep(3)
                try:
                    el_error = driver.find_element_by_css_selector(".ui-form-explain")
                    print el_error.text
                    if not el_error.text:
                        break
                except Exception, e:
                    break

def login_pay_wap(driver, order_info):
    try:
        obj = driver.find_element_by_link_text("使用其他方式登录")
    except:
        obj = driver.find_element_by_link_text("支付宝账户登录")
    driver.get(obj.get_attribute("href"))

    if "loginIdPwdToLogin" in driver.current_url: # 账号密码登陆页
        el_name= WebDriverWait(driver, 10).until(EC.presence_of_element_located((By.ID, "logon_id")))
        el_name.send_keys(driver.alipay_account)
        el_pwd = driver.find_element_by_id("pwd_unencrypt")
        el_pwd.clear()
        el_pwd.send_keys(driver.alipay_paypwd)

        while 1:
            el_btn = driver.find_element_by_xpath("//button[@type='submit']")
            try:
                el_code = driver.find_element_by_id("omeoCheckcode")
            except:
                el_btn.submit()
                break

            el_code.clear()
            el_code.send_keys(raw_input("请输入图片验证码:"))
            el_btn.click()
            try:
                msg = driver.find_element_by_css_selector(".am-msg-box").text
            except:
                msg = ""
            if not msg:
                break

def pay_wap(driver, order_info):

    def pay_detail(driver, order_info):
        el_btn = driver.find_element_by_xpath("//button[@type='submit']")
        el_btn.click()

    def input_paypwd(driver, order_info):
        try:
            el_pwd = driver.find_element_by_id("pwd_unencrypt")
        except:
            el_pwd = driver.find_element_by_id("spwd_unencrypt")

        el_pwd.clear()
        el_pwd.send_keys(driver.alipay_paypwd)

        try:
            el_btn = driver.find_element_by_xpath("//button[text()='确定']")
        except:
            el_btn = None
        try:
            el_code = driver.find_element_by_id("omeoCheckcode")
        except:
            if el_btn:
                el_btn.submit()
            return
        el_code.clear()
        el_code.send_keys(raw_input("请输入图片验证码:"))
        el_btn.click()

        try:
            el_btn = driver.find_element_by_xpath("//a[text()='确定']")
            el_btn.click()
        except:
            el_btn = None

    def input_smscode(driver, order_info):
        el_code = WebDriverWait(driver, 1).until(EC.presence_of_element_located((By.ID, "smsCode")))
        while 1:
            el_code.clear()
            el_code.send_keys(raw_input("请输入短信验证码:"))
            el_btn = driver.find_element_by_xpath("//button[@type='submit']")
            el_btn.click()
            frames = driver.find_elements_by_tag_name("iframe")
            if len(frames) >1:  # 有弹框
                driver.switch_to_frame(frames[1])
                import pdb;pdb.set_trace()
                continue
            break

    def pay_result(driver, order_info):
        driver.payed_orders[order_info["order_no"]] = time.time()

    def pay_result2(driver, order_info):
        try:
            error = driver.find_element_by_class_name("am-message-error").text
            if "交易已经支付" in error:
                driver.payed_orders[order_info["order_no"]] = time.time()
        except:
            pass

    op_func = {
        u"登录支付宝": login_pay_wap,
        u"付款详情": pay_detail,
        u"输入支付密码": input_paypwd,
        u"短信校验码": input_smscode,
        u"付款结果": pay_result,
        u"支付宝": pay_result2,
    }
    tmp = {}
    while 1:
        time.sleep(2)
        page_meta = driver.find_element_by_css_selector(".am-header .title-main").text
        op_func[page_meta](driver, order_info)
        tmp[page_meta] = tmp.get(page_meta, 0) + 1
        if page_meta == u"付款结果":
            break
        if tmp[page_meta]>5:
            break

def pay(driver, order_info):
    order_no = order_info["order_no"]
    driver.try_pay_times[order_no] = driver.try_pay_times.get(order_no, 0) + 1
    if driver.try_pay_times[order_no]>60:
        msg = "尝试次数超过限制"
        if order_no in driver.payed_orders:
            msg = "已支付,未出票"
        elif order_info["status"] in [7, 4]:
            msg = "无法正常下单"
        succ = give_to_other(driver, order_info, msg)
        if succ:
            driver.try_pay_times[order_no] = 0
        print "尝试转给他人", succ

    if order_no in driver.payed_orders:
        return
    source = order_info["crawl_source"]
    if source in ["scqcp"]:
        return

    try:
        url = "%s/orders/%s/pay" % (DASHBOARD_URL, order_no)
        driver.get(url)
    except Exception, e:
        print e
        return
    try:

        if "cashiersu18" in driver.current_url or "cashiergtj" in driver.current_url or "cashierzth" in driver.current_url or 'cashierzui' in driver.current_url:
            pay_pc(driver, order_info)
        elif "mclient" in driver.current_url or "wappaygw" in driver.current_url:
            pay_wap(driver, order_info)
    except UnexpectedAlertPresentException, e:
        print e
        try:
            alert = driver.switch_to_alert()
            alert.accept()
        except:
            pass
    except Exception, e:
        print e


def check_alipay_status(driver):
    if not hasattr(driver, "last_check_time"):
        driver.last_check_time =  dte.now()

    if (dte.now() - driver.last_check_time).total_seconds() < 30:
        return
    driver.last_check_time = dte.now()

    try:
        if driver.alipay_account in ["kuo86106@qq.com", "a13267109876@sohu.com"]:
            url = "https://uemprod.alipay.com/user/ihome.htm"
            driver.get(url)
            yue = float(driver.find_element_by_css_selector(".usable-balance span em").text.replace(",",""))
            yuebao = 0
            account = driver.alipay_account
            username = driver.dashboard_account
        else:
            url = "https://my.alipay.com/portal/i.htm"
            driver.get(url)
            yue = float(driver.find_element_by_css_selector(".i-assets-balance-amount .amount").text)
            yuebao = float(driver.find_element_by_css_selector("#J-assets-mfund-amount .amount").text)
            account = driver.alipay_account
            username = driver.dashboard_account
        driver.alipay_online = True
        requests.get(DASHBOARD_URL+"/users/config?type=api&action=refresh&username=%s&account=%s&yue=%s&yuebao=%s" % (username, account, yue, yuebao), headers={"token": driver.dashboard_token}, timeout=30)
    except Exception, e:
        print e
        driver.alipay_online = False
