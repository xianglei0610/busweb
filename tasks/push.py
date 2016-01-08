# -*- coding:utf-8 -*-
import urllib2
import json
import datetime
import random
import traceback
try:
    from igetui.igt_push import *
    from igetui.template.igt_transmission_template import *
    from igetui.template.igt_link_template import *
    from igetui.template.igt_notification_template import *
    from igetui.template.igt_notypopload_template import *
    from igetui.template.igt_apn_template import *
    from igetui.igt_message import *
    from igetui.igt_target import *
    from igetui.BatchImpl import *
    from igetui.payload.APNPayload import *
except:
    pass
from app.constants import HOST, AppKey, AppID, MasterSecret, AppSecret
from app import celery
from app.utils import getRedisObj
from app.models import PushUserList, Order


def TransmissionTemplateDemo(order_no):
    template = TransmissionTemplate()
    template.transmissionType = 2
    template.appId = AppID
    template.appKey = AppKey
    template.transmissionContent = '订单来啦'
    # iOS 推送需要的PushInfo字段 前三项必填，后四项可以填空字符串
    # template.setPushInfo(actionLocKey, badge, message, sound, payload, locKey, locArgs, launchImage)
#     template.setPushInfo("", 0, "", "com.gexin.ios.silence", "", "", "", "");

# APN简单推送
    alertMsg = SimpleAlertMsg()
    alertMsg.alertMsg = '订单来啦'
    apn = APNPayload()
    apn.alertMsg = alertMsg
    apn.badge = 1
#     apn.sound = ""
    apn.addCustomMsg("payload", "payload")
#     apn.contentAvailable=1
#     apn.category="ACTIONABLE"
    template.setApnInfo(apn)

    # APN高级推送
#     apnpayload = APNPayload()
#     apnpayload.badge = 4
#     apnpayload.sound = "com.gexin.ios.silence"
#     apnpayload.addCustomMsg("payload", "payload")
# #     apnpayload.contentAvailable = 1
# #     apnpayload.category = "ACTIONABLE"
#     alertMsg = DictionaryAlertMsg()
#     alertMsg.body = 'body'
#     alertMsg.actionLocKey = 'actionLockey'
#     alertMsg.locKey = 'lockey'
#     alertMsg.locArgs=['locArgs']
#     alertMsg.launchImage = 'launchImage'
#     # IOS8.2以上版本支持
# #     alertMsg.title = 'Title'
# #     alertMsg.titleLocArgs = ['TitleLocArg']
# #     alertMsg.titleLocKey = 'TitleLocKey'
#     apnpayload.alertMsg=alertMsg
#     template.setApnInfo(apnpayload)

    return template


@celery.task(bind=True, ignore_result=True)
def push_kefu_order(self, username, order_no):
    pushobj = PushUserList.objects.get(username=username)
    order = Order.objects.get(order_no=order_no)
    push = IGeTui(HOST, AppKey, MasterSecret)
    # 消息模版：
    # 1.TransmissionTemplate:透传功能模板
    # 2.LinkTemplate:通知打开链接功能模板
    # 3.NotificationTemplate：通知透传功能模板
    # 4.NotyPopLoadTemplate：通知弹框下载功能模板

#     template = NotificationTemplateDemo()
    # template = LinkTemplateDemo()
    template = TransmissionTemplateDemo(order.order_no)
    # template = NotyPopLoadTemplateDemo()

    message = IGtSingleMessage()
    message.isOffline = True
    message.offlineExpireTime = 1000 * 3600 * 12
    message.data = template
    # message.pushNetWorkType = 2

    target = Target()
    target.appId = AppID
    target.clientId = pushobj.push_id

    try:
        ret = push.pushMessageToSingle(message, target)
        print ret
    except RequestException, e:
        requstId = e.getRequestId()
        ret = push.pushMessageToSingle(message, target, requstId)
        print ret




