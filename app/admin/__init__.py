# -*- coding:utf-8 -*-
import jinja2

from flask import Blueprint

admin = Blueprint('admin', __name__)

import views, errors


# =========================filter=====================
@jinja2.contextfilter
@admin.app_template_filter()
def format_datetime(context, value, format="%Y-%m-%d %H:%M"):
    return value.strftime(format)
