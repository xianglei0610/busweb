# -*- coding:utf-8 -*-

from flask import Blueprint, request
from app import access_log

api = Blueprint('api', __name__)

import views, errors

# =================middleware ===================


@api.before_request
def log_request():
    access_log.debug("[request]%s %s %s", request.method, request.url, request.data)


@api.after_request
def log_response(response):
    access_log.debug("[response]%s", response.get_data()[:1000])
    return response
