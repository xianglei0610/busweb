#!/usr/bin/env python
# -*- coding:utf-8 *-*
import os
import sys
import pymongo
import multiprocessing

from datetime import datetime
from app import setup_app, db
from app.utils import md5
from flask.ext.script import Manager, Shell

BASE_DIR = os.path.abspath(os.path.dirname(__file__))
app = setup_app(os.getenv('FLASK_CONFIG') or 'local',
                os.getenv('FLASK_SERVER') or 'api')
manager = Manager(app)


def make_shell_context():
    import app.models as m
    return dict(app=app, db=db, m=m)

manager.add_command("shell", Shell(make_context=make_shell_context))


@manager.command
def deploy():
    from app.models import ScqcpRebot, Bus100Rebot
    ScqcpRebot.login_all()
    Bus100Rebot.login_all()


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
        u.is_admin = 0
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


@manager.command
def migrate_from_crawl(site):
    settings = app.config["CRAWL_MONGODB_SETTINGS"]
    crawl_mongo = pymongo.MongoClient("mongodb://%s:%s" % (settings["host"], settings["port"]))
    crawl_db = crawl_mongo[settings["db"]]

    from sync_data import migrate_bus100, migrate_scqcp, migrate_ctrip
    mappings = {
        "scqcp": migrate_scqcp,
        "bus100": migrate_bus100,
        "ctrip": migrate_ctrip,
    }
    app.logger.info("start migrate data from crawldb to webdb:%s", site)
    mappings[site](crawl_db)
    app.logger.info("end migrate %s" % site)


if __name__ == '__main__':
    manager.run()
