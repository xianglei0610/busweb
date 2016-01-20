#!/usr/bin/env python
# -*- coding: utf-8 -*-


# 错误码详情
DETAILS = {
    101: {
        'msg': u'客户端网络故障',
        'retry': True,
    },
    303: {
        'msg': u'客户端网络故障',
        'retry': True,
    },
    305: {
        'msg': u'服务器端返回错误，错误的返回值（返回值不是数字字符串）',
        'retry': False,
    },
    307: {
        'msg': u'目标电话号码不符合规则，电话号码必须是以0、1开头',
        'retry': False,
    },
    997: {
        'msg': u'平台返回找不到超时的短信，该信息是否成功无法确定',
        'retry': False,
    },
    998: {
        'msg': u'由于客户端网络问题导致信息发送超时，该信息是否成功下发无法确定',
        'retry': True,
    },
    999: {
        'msg': u'操作频繁',
        'retry': False,
    },
    -1: {
        'msg': u'系统异常',
        'retry': True,
    },
    -2: {
        'msg': u'客户端异常',
        'retry': True,
    },
    -101: {
        'msg': u'命令不被支持',
        'retry': False,
    },
    -104: {
        'msg': u'请求超过限制',
        'retry': False,
    },
    -110: {
        'msg': u'号码注册激活失败',
        'retry': True,
    },
    -117: {
        'msg': u'发送短信失败',
        'retry': True,
    },
    -122: {
        'msg': u'号码注销激活失败',
        'retry': False,
    },
    -126: {
        'msg': u'路由信息失败',
        'retry': True,
    },
    -190: {
        'msg': u'数据操作失败',
        'retry': False,
    },
    -1100: {
        'msg': u'序列号错误，序列号不存在内存中，或尝试攻击的用户',
        'retry': False,
    },
    -1103: {
        'msg': u'序列号Key错误',
        'retry': False,
    },
    -1102: {
        'msg': u'序列号密码错误',
        'retry': False,
    },
    -1104: {
        'msg': u'路由失败，请联系系统管理员',
        'retry': False,
    },
    -1105: {
        'msg': u'注册号状态异常, 未用 1',
        'retry': False,
    },
    -1107: {
        'msg': u'注册号状态异常, 停用 3',
        'retry': False,
    },
    -1108: {
        'msg': u'注册号状态异常, 停止 5',
        'retry': False,
    },
    -1901: {
        'msg': u'数据库插入操作失败',
        'retry': False,
    },
    -1902: {
        'msg': u'数据库更新操作失败',
        'retry': False,
    },
    -9001: {
        'msg': u'序列号格式错误',
        'retry': False,
    },
    -9002: {
        'msg': u'密码格式错误',
        'retry': False,
    },
    -9003: {
        'msg': u'客户端Key格式错误',
        'retry': False,
    },
    -9016: {
        'msg': u'发送短信包大小超出范围',
        'retry': True,
    },
    -9017: {
        'msg': u'发送短信内容格式错误',
        'retry': False,
    },
    -9018: {
        'msg': u'发送短信扩展号格式错误',
        'retry': False,
    },
    -9019: {
        'msg': u'发送短信优先级格式错误',
        'retry': False,
    },
    -9020: {
        'msg': u'发送短信手机号格式错误',
        'retry': False,
    },
    -9021: {
        'msg': u'发送短信定时时间格式错误',
        'retry': False,
    },
    -9022: {
        'msg': u'发送短信唯一序列值错误',
        'retry': False,
    },
    -9025: {
        'msg': u'客户端请求sdk5超时',
        'retry': True,
    },
}


# 方法错误码
CODES = {
    'regist_ex': [
        101, 303,
        305,
        999,
        -1,
        -2,
        -101,
        -104,
        -110,
        -126,
        -190,
        -1100,
        -1103,
        -1102,
        -1104,
        -1105,
        -1107,
        -1108,
        -1901,
        -9001,
        -9002,
        -9025,
        -9003,
    ],
    'send_sms': [
        305,
        101, 303,
        307,
        997,
        998,
        -1,
        -2,
        -101,
        -104,
        -117,
        -1104,
        -9016,
        -9017,
        -9018,
        -9019,
        -9020,
        -9021,
        -9022,
        -9001,
        -9002,
        -9003,
        -9025,
    ],
    'logout': [
        101, 303,
        305,
        999,
        -1,
        -2,
        -101,
        -104,
        -122,
        -126,
        -1104,
        -190,
        -1902,
        -9001,
        -9002,
        -9003,
        -9025,
        -1100,
    ],
}


def get_errors(method_name, code):
    """ 获取错误信息

    参数:
        method_name  方法名
        code         错误码
    """
    if method_name in CODES:
        if code in CODES[method_name]:
            return DETAILS[code]

    return {
        'msg': u'未知错误',
        'retry': False
    }
