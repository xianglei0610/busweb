#!/usr/bin/env python
# -*- coding:utf-8 *-*
import os
import pymongo

from app import setup_app, db
from flask.ext.script import Manager, Shell
from datetime import datetime as dte

BASE_DIR = os.path.abspath(os.path.dirname(__file__))
app = setup_app()
manager = Manager(app)


def make_shell_context():
    import app.models as m
    import app.flow as f
    return dict(app=app, db=db, m=m, f=f)

manager.add_command("shell", Shell(make_context=make_shell_context))


@manager.command
def deploy(site):
    from app.models import ScqcpRebot, Bus100Rebot, CTripRebot, CBDRebot, JskyAppRebot, JskyWebRebot
    if site == "ctrip":
        CTripRebot.login_all()
    elif site == "scqcp":
        ScqcpRebot.login_all()
    elif site == "bus100":
        Bus100Rebot.login_all()
    elif site == "cbd":
        CBDRebot.login_all()
    elif site == "jskyapp":
        JskyAppRebot.login_all()
    elif site == "jskyweb":
        JskyWebRebot.login_all()
    elif site == "babaweb":
        from app.models import BabaWebRebot
        BabaWebRebot.login_all()


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
        u.is_kefu = 1
        u.is_switch = 0
        u.is_admin = 1
    elif type == "admin":
        u.is_kefu = 0
        u.is_switch = 0
        u.is_admin = 1

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


@manager.option('-s', '--site', dest='site', default='')
@manager.option('-c', '--city', dest='city', default='')
def migrate_from_crawl(site, city=""):
    settings = app.config["CRAWL_MONGODB_SETTINGS"]
    crawl_mongo = pymongo.MongoClient("mongodb://%s:%s" % (settings["host"], settings["port"]))
    crawl_db = crawl_mongo[settings["db"]]

    from sync_data import migrate_bus100, migrate_scqcp, migrate_ctrip, migrate_cbd, migrate_jsky
    mappings = {
        "scqcp": migrate_scqcp,
        "bus100": migrate_bus100,
        "ctrip": migrate_ctrip,
        "cbd": migrate_cbd,
        "jsky": migrate_jsky,
    }
    app.logger.info("start migrate data from crawldb to webdb:%s", site)
    mappings[site](crawl_db, city=city)
    app.logger.info("end migrate %s" % site)


@manager.command
def clear_expire_line():
    from app.models import Line
    now = dte.now()
    print Line.objects.filter(crawl_datetime__lte=now).delete()


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
        openObj.pre_sell_days = 10
        openObj.open_time = "23:00"
        openObj.end_time = "8:00"
        openObj.advance_order_time = 0
        openObj.max_ticket_per_order = 5
        openObj.crawl_source = site
        openObj.is_active = True
        try:
            openObj.save()
            print openObj.city_name
        except:
            print '%s already existed'%city_name
            pass


if __name__ == '__main__':
    manager.run()
