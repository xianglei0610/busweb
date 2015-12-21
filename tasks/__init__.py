# -*- coding:utf-8 -*-
"""
celery任务模块
"""
from ticket import lock_ticket, issued_callback
from order import check_order_expire, refresh_kefu_order
