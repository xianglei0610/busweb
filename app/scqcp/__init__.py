# -*- coding:utf-8 -*-

from flask import Blueprint

scqcp = Blueprint('scqcp', __name__)

import views, errors
