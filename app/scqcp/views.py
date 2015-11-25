# -*- coding:utf-8 -*-

from app.scqcp import scqcp


def get_ticket_info(carry_sta_id, stop_name, sign_id, drv_date):
    "获取票价信息"
    pass


# rider_name=罗军平&id_type=0&id_number=431021199004165616&birthday=1990-04-16
def set_riders(riders):
    pass


@scqcp.route('/lines/<line_pk>/post_order/', methods=['POST'])
def post_order(line_pk):
    """
    向scqcp.com下订单
    """
    pass


@scqcp.route('/order/<order_pk>/pay/', methods=['POST'])
def pay(order_pk):
    """
    向scqcp.com支付
    """
    pass
