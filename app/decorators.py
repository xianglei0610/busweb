# -*- coding:utf-8 -*-
import threading

from functools import wraps
from flask import current_app, flash
from flask.ext.login import current_user


def async(func):
    def _wrap(*args, **kwargs):
        t = threading.Thread(target=func, args=args, kwargs=kwargs)
        t.start()
    return _wrap


def superuser_required(func):
    '''
    要求超级管理员权限
    '''
    @wraps(func)
    def decorated_view(*args, **kwargs):
        if not current_user.is_authenticated:
            return current_app.login_manager.unauthorized()
        elif not current_user.is_superuser:
            return current_app.login_manager.unauthorized()
        return func(*args, **kwargs)
    return decorated_view
