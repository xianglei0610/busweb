# -*- coding:utf-8 -*-
from app import login_manager
from app.models import AdminUser
from app.utils import get_redis

login_manager.login_view = "dashboard.login"

login_manager.login_message = "您没权限打开此页面"


@login_manager.user_loader
def load_admin(username):
    try:
        u = AdminUser.objects.get(username=username)
    except AdminUser.DoesNotExist:
        return
    return u


@login_manager.request_loader
def request_loader(request):
    token = request.headers.get("token", "")
    if not token:
        return None
    key = "token%s" % token
    rds = get_redis("default")
    try:
        u = AdminUser.objects.get(username=rds.get(key))
        rds.expire(key, 24*60*60)
    except AdminUser.DoesNotExist:
        return None
    return u
