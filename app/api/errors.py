# -*- coding:utf-8 -*-
from app.constants import *
from app.api import api

from flask import jsonify


@api.app_errorhandler(404)
def page_not_found(e):
    return jsonify({"code": RET_PAGE_404, "message": "page not found", "data": ""})


@api.app_errorhandler(500)
def internal_server_error(e):
    print e
    return jsonify({"code": RET_SERVER_ERROR, "message": "服务器异常", "data": ""})
