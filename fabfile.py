#!/usr/bin/env python
# encoding: utf-8

from fabric.api import env
from fabric.operations import run
from fabric.context_managers import cd
from fabric.api import execute

SERVER_LIST = {
    "banana": "120.27.150.94",
    "apple": "114.55.74.162",
    "orange": "120.26.58.41",
}

env.user = '12308'
env.hosts = SERVER_LIST.values()


def update_code():
    run("git checkout master")
    run("git fetch")
    run("git reset --hard origin/master")


def deploy(name=""):
    if name not in ("admin", "api", "celery"):
        raise Exception("name should be in (admin, api, celery), but it's %s" % name)

    with cd("/home/12308/code/busweb/"):
        # 拉代码
        run("git checkout master")
        run("git fetch")
        run("git merge origin/master")

        # 重启supervisor
        run("sudo supervisorctl restart server:%s" % name)


def deploy_all():
    execute(deploy, "api")
    execute(deploy, "admin")
    execute(deploy, "celery")
