#!/usr/bin/env python
# -*- coding: utf-8 -*-
import sys
reload(sys)
sys.setdefaultencoding('utf8')

from suds.client import Client

from config import URL, SERIAL_NO, KEY, PASSWORD
from errors import get_errors


SRV = Client(URL).service


class SmsException(Exception):
    """ 短信异常类
    """
    pass


def retry(max_times=5):
    """ 重试装饰器

    如果遇到“`method`返回错误，但允许重试的情况”，则进行重试（最多重试`max_times`次）
    """
    def wrapper(method):
        def inner(*args, **kwargs):
            result = method(*args, **kwargs)

            if result != 0:
                err = get_errors(method.__name__, result)
                if err['retry'] and method.ncalls < max_times:
                    method.ncalls += 1
                    inner(*args, **kwargs)
                else:
                    raise SmsException(err['msg'])

        method.ncalls = 0
        return inner

    return wrapper


@retry()
def regist_ex():
    """ 注册序列号
    """
    return SRV.registEx(
        SERIAL_NO,
        KEY,
        PASSWORD
    )


@retry(3)
def send_sms(mobiles, content, sms_id):
    """ 发送短信
    """
    return SRV.sendSMS(
        SERIAL_NO,
        KEY,
        '',
        mobiles,
        content,
        '',
        'GBK',
        1,
        sms_id
    )


def get_report(callback):
    result = SRV.getReport(SERIAL_NO, KEY)
    if result:
        callback(result)
    return result


@retry(0)
def logout():
    """ 注销序列号
    """
    return SRV.logout(SERIAL_NO, KEY)

def send_msg(sms_phone_list, content):
#     sms_phone_list = ['13267109876']
#     content = u'【乐程票务】你好23，你的3码为128989'
#     id = regist_ex()
    print sms_phone_list, content,type(content)
    send_sms(sms_phone_list, content, 1452444)
#     logout()
if __name__ == '__main__':
    # 注册
    id = regist_ex()
    sms_phone_list = ['13267109876']

    # 发送
    print(send_sms(
        sms_phone_list,
        u'【乐程票务】你好23，你的3码为128989',
        1452444
    ))
    logout()
    # 获取状态报告
    '''def callback(result):
        print result

    import time
    try:
        while True:
            if get_report(callback):
                break
            time.sleep(5)
    finally:
        # 注销
        logout()'''
