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
def cut_str(context, value, size=20):
    if not value:
        return value
    if len(value) < size:
        return value
    return value[:size]+"..."


@jinja2.contextfilter
@dashboard.app_template_filter()
def bitor(context, value, target):
    return value&target

@jinja2.contextfilter
@dashboard.app_template_filter()
def percent_divide(context, value, target):
    if not target:
        return "100%"
    return "%.2f%%" % (value*100/float(target))

@dashboard.after_request
def log_response(response):
    return response
