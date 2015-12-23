# -*- coding:utf-8 -*-
import jinja2

from flask import Blueprint, request
from app import access_log

admin = Blueprint('admin', __name__)

import views, errors, auth


# =========================filter=====================
@jinja2.contextfilter
@admin.app_template_filter()
def format_datetime(context, value, format="%Y-%m-%d %H:%M:%S"):
    if not value:
        return ""
    return value.strftime(format)


@admin.before_request
def log_request():
    access_log.debug("[request]%s %s %s", request.method, request.url, request.data)


@admin.after_request
def log_response(response):
    access_log.debug("[response]%s", response.get_data()[:1000])
    return response
