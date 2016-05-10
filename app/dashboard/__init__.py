# -*- coding:utf-8 -*-
import jinja2

from flask import Blueprint

dashboard = Blueprint('dashboard', __name__)

import views, errors, auth


# =========================filter=====================
@jinja2.contextfilter
@dashboard.app_template_filter()
def format_datetime(context, value, format="%Y-%m-%d %H:%M:%S"):
    if not value:
        return ""
    return value.strftime(format)


@jinja2.contextfilter
@dashboard.app_template_filter()
def cut_str(context, value, size=22):
    if not value:
        return value
    if len(value) < size:
        return value
    return value[:size]+"..."


@dashboard.before_request
def log_request():
    pass


@dashboard.after_request
def log_response(response):
    return response
