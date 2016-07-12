#!/usr/bin/env python
# encoding: utf-8

from fabric.api import env
from fabric.operations import run
from fabric.context_managers import cd

SERVER_LIST = {
    "banana": "120.27.150.94",
    "apple": "114.55.74.162",
    "pear": "114.55.100.171",
}

env.user = '12308'
env.hosts = SERVER_LIST.values()


def deploy(name=""):
    if name not in ("api", "celery", "dashboard", "cron"):
        raise Exception("name should be in (api, celery, dashboard), but it's %s" % name)

    with cd("/home/12308/code/busweb/"):
        # 拉代码
        run("git checkout master")
        run("git fetch")
        run("git merge origin/master")

        # 重启supervisor
        if name == "cron":
            if env.host == "114.55.74.162":
                run("sudo supervisorctl restart scrapy:cron")
        else:
            run("sudo supervisorctl restart server:%s" % name)


def deploy_all():
    with cd("/home/12308/code/busweb/"):
        # 拉代码
        run("git checkout master")
        run("git fetch")
        run("git merge origin/master")

        for name in ["api", "celery", "dashboard"]:
            # 重启supervisor
            run("sudo supervisorctl restart server:%s" % name)

        if env.host == "114.55.74.162":
            run("sudo supervisorctl restart scrapy:cron")
