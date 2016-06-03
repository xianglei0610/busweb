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
    if name not in ("admin", "api", "celery", "dashboard"):
        raise Exception("name should be in (admin, api, celery), but it's %s" % name)

    with cd("/home/12308/code/busweb/"):
        # 拉代码
        run("git checkout master")
        run("git fetch")
        run("git merge origin/master")

        # 重启supervisor
        run("sudo supervisorctl restart server:%s" % name)


def deploy_all():
    with cd("/home/12308/code/busweb/"):
        # 拉代码
        run("git checkout master")
        run("git fetch")
        run("git merge origin/master")

        for name in ["admin", "api", "celery", "dashboard"]:
            # 重启supervisor
            run("sudo supervisorctl restart server:%s" % name)
