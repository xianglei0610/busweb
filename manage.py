#!/usr/bin/env python
# -*- coding:utf-8 *-*
import os
import zipfile

from app import setup_app, db
from flask.ext.script import Manager, Shell
from datetime import datetime as dte
from app.constants import *


BASE_DIR = os.path.abspath(os.path.dirname(__file__))
app = setup_app()
manager = Manager(app)


def make_shell_context():
    import app.models as m
    import app.flow as f
    get_order = lambda o: m.Order.objects.get(order_no=o)
    get_line = lambda o: m.Line.objects.get(line_id=o)
    def make_fail(o, type):
        order = get_order(o)
        if order.status not in [7, 3, 12]:
            return
        if type == "lock":
            order.update(status=5)
        elif type == "issue":
            order.update(status=13)
        else:
            return
        from tasks import issued_callback
        issued_callback(o)
    return dict(app=app, db=db, m=m, f=f, get_order=get_order, get_line=get_line, make_fail=make_fail)

manager.add_command("shell", Shell(make_context=make_shell_context))


@manager.command
def init_account(site):
    from app.models import get_rebot_class
    for cls in get_rebot_class(site):
        cls.login_all()


@manager.command
def cron():
    from cron import main
    main()


@manager.command
def test(coverage=False):
    cov = None
    if coverage:
        import coverage
        cov = coverage.coverage(branch=True, include="app/*")
        cov.start()
    import unittest
    tests = unittest.TestLoader().discover("tests")
    unittest.TextTestRunner(verbosity=2).run(tests)
    if cov:
        cov.stop()
        cov.save()
        print "coverage test result:"
        cov.report()
        covdir = os.path.join(BASE_DIR, 'tmp/covrage')
        cov.html_report(directory=covdir)
        print "Html version: file://%s/index.html" % covdir
        cov.erase()


@manager.command
def create_user(type):
    import getpass
    from app.models import AdminUser
    from app.utils import md5
    if type not in ["kefu", "admin"]:
        print "fail, the right command should like 'python manage.py create_user (kefu or admin)'"
        return
    username = raw_input("用户名:")
    try:
        u = AdminUser.objects.get(username=username)
        print "已存在用户, 创建失败"
        return
    except AdminUser.DoesNotExist:
        pass
    pwd1 = getpass.getpass('密码: ')
    pwd2 = getpass.getpass('确认密码: ')
    if pwd1 != pwd2:
        print "两次输入密码不一致, 创建用户失败"
        return
    u = AdminUser(username=username, password=md5(pwd1))
    if type == "kefu":
        u.is_switch = 0
    elif type == "admin":
        u.is_switch = 0

    u.save()
    print "创建用户成功"


@manager.command
def reset_password():
    import getpass
    from app.models import AdminUser
    from app.utils import md5
    username = raw_input("用户名:")
    try:
        u = AdminUser.objects.get(username=username)
        pwd1 = getpass.getpass('密码: ')
        pwd2 = getpass.getpass('确认密码: ')
        if pwd1 != pwd2:
            print "两次输入密码不一致, 重设密码失败"
            return
        u.modify(password=md5(pwd1))
        print "重设密码成功"
    except AdminUser.DoesNotExist:
        print "不存在用户", username


@manager.command
def clear_expire_line():
    from app.models import Line
    today = dte.now().strftime("%Y-%m-%d")
    cnt = Line.objects.filter(drv_date__lt=today).delete()
    app.logger.info("%s line deleted", cnt)


@manager.command
def add_pay_record(directory):
    from pay import import_alipay_record
    for par, dirs, files in os.walk(directory):
        for name in files:
            filename = os.path.join(par, name)
            if filename.endswith(".zip"):
                z = zipfile.ZipFile(filename, "r")
                for filename in z.namelist():
                    with z.open(filename) as f:
                        import_alipay_record(f)
            else:
                with open(filename, "r") as f:
                    import_alipay_record(f)


@manager.option('-s', '--site', dest='site', default='')
@manager.option('-p', '--province_name', dest='province_name',default='')
def sync_open_city(site, province_name):
    from app.models import OpenCity, Line
    from pypinyin import lazy_pinyin
    if not province_name:
        print 'province_name is null '
        return
    lines = Line.objects.filter(crawl_source=site, s_province=province_name).distinct('s_city_name')
    print lines
    for i in lines:
        openObj = OpenCity()
        openObj.province = province_name
        city_name = i
        if len(city_name) > 2 and (city_name.endswith('市') or city_name.endswith('县')):
            city_name = city_name[0:-1]
        openObj.city_name = city_name
        city_code = "".join(map(lambda w: w[0], lazy_pinyin(city_name.decode("utf-8"))))
        openObj.city_code = city_code
        openObj.pre_sell_days = 4
        openObj.open_time = "23:00"
        openObj.end_time = "8:00"
        openObj.advance_order_time = 60
        openObj.max_ticket_per_order = 3
        openObj.crawl_source = site
        openObj.is_active = True
        try:
            openObj.save()
            print openObj.city_name
        except:
            print '%s already existed'%city_name
            pass

@manager.command
def make_success(order_no):
    from app.models import Order
    order = Order.objects.get(order_no=order_no)
    if order.status !=  STATUS_WAITING_ISSUE:
        print "状态不对"
        return
    code1 = raw_input("请输入取票密码:")
    code = raw_input("请再次输入取票密码:")
    if code1 != code:
        print "两次输入密码不一致"
        return
    dx_info = {
        "time": order.drv_datetime.strftime("%Y-%m-%d %H:%M"),
        "start": order.line.s_sta_name,
        "end": order.line.d_sta_name,
        "code": code,
        'raw_order': order.raw_order_no,
    }
    dx_tmpl = DUAN_XIN_TEMPL[SOURCE_HN96520]
    code_list = ["%s" % (code)]
    msg_list = [dx_tmpl % dx_info]
    print msg_list[0]
    order.modify(status=STATUS_ISSUE_SUCC,
                    pick_code_list=code_list,
                    pick_msg_list=msg_list)
    order.on_issue_success()
    from tasks import issued_callback
    issued_callback.delay(order.order_no)


if __name__ == '__main__':
    manager.run()
