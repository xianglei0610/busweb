# -*- coding:utf-8 -*-
from app import login_manager
from app.models import AdminUser


@login_manager.user_loader
def load_admin(username):
    return AdminUser.objects.get(username=username)
