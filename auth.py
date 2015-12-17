# -*- coding:utf-8 -*-
from app import login_manager
from app.models import AdminUser
from app.utils import md5

login_manager.login_view = "admin.login"


@login_manager.user_loader
def load_admin(username):
    try:
        u = AdminUser.objects.get(username=username)
    except AdminUser.DoesNotExist:
        return
    return u


@login_manager.request_loader
def request_loader(request):
    name = request.form.get("username")
    pwd = request.form.get("password")
    if not name or not pwd:
        return
    try:
        u = AdminUser.objects.get(username=name, password=md5(pwd))
    except AdminUser.DoesNotExist:
        return None
    u.is_authenticated = True
    return u
