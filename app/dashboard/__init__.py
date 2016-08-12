# -*- coding:utf-8 -*-
import jinja2

from app.constants import *
from flask import Blueprint
from flask import jsonify
from flask import render_template, request, redirect, url_for, jsonify, session, make_response, flash

dashboard = Blueprint('dashboard', __name__)

import views, auth


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


@dashboard.app_errorhandler(404)
def page_not_found(e):
    return jsonify({"code": RET_PAGE_404, "message": "page not found", "data": ""})


@dashboard.app_errorhandler(500)
def internal_server_error(e):
    print request.url
    kwargs = {
        "title": "500错误",
        "message": "打开 %s 报错, 请联系技术" % request.path,
    }
    return render_template('dashboard/error.html', **kwargs)
