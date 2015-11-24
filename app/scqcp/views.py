# -*- coding:utf-8 -*-

from app.scqcp import scqcp


@scqcp.route('/', methods=['GET', 'POST'])
def index():
    pass
