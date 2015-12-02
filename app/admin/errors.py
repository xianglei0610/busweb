# -*- coding:utf-8 -*-
from app.constants import *
from app.admin import admin

from flask import jsonify


@admin.app_errorhandler(404)
def page_not_found(e):
    return jsonify({"code": RET_PAGE_404, "message": "page not found", "data": ""})


@admin.app_errorhandler(500)
def internal_server_error(e):
    return jsonify({"code": RET_SERVER_ERROR, "message": "服务器异常", "data": ""})
