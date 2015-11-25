# -*- coding:utf-8 -*-
import urllib2
import urllib
import random

from datetime import datetime
from flask import current_app, json

from app.constans import SCQCP_ACCOUNTS
from app.constans import SCQCP_DOMAIN, MOBILE_USER_AGENG
from app import db


class ScqcpRebot(db.Document):
    """
    针对四川汽车票务网的Rebot
    """
    telephone = db.StringField(required=True, unique=True)
    password = db.StringField()
    is_encrypt = db.IntField(choices=(0, 1))
    user_agent = db.StringField()
    token = db.StringField()
    open_id = db.StringField()
    is_active = db.BooleanField(default=True)  # 是否已被删除
    last_login_time = db.DateTimeField(default=datetime.now)

    meta = {
        "indexes": [("telephone", "password"), ],
    }

    def relogin(self):
        """
        返回OK表示登陆成功
        """
        ua = random.choice(MOBILE_USER_AGENG)
        device = "android" if "android" in ua else "ios"

        # 获取token
        uri = "/api/v1/api_token/get_token_for_app?channel=dxcd&version_code=40&oper_system=%s" % device
        url = urllib2.urlparse.urljoin(SCQCP_DOMAIN, uri)
        request = urllib2.Request(url)
        request.add_header('User-Agent', ua)
        response = urllib2.urlopen(request, timeout=5)
        ret = json.loads(response.read())
        token = ret["token"]

        # 登陆
        uri = "/api/v1/user/login_phone"
        url = urllib2.urlparse.urljoin(SCQCP_DOMAIN, uri)
        request = urllib2.Request(url)
        request.add_header('User-Agent', ua)
        request.add_header('Authorization', token)
        request.add_header('Content-type', "application/json; charset=UTF-8")
        data = {
            "username": self.telephone,
            "password": self.password,
            "is_encrypt": self.is_encrypt,
        }
        qstr = urllib.urlencode(data)
        response = urllib2.urlopen(request, qstr, timeout=5)
        ret = json.loads(response.read())
        if "open_id" not in ret:
            # 登陆失败
            current_app.logger.error("%s %s login scqcp.com failed! %s", self.telephone, self.password, ret.get("msg", ""))
            self.update(is_active=False)
            return ret.get("msg", "fail")
        open_id = ret["open_id"]

        self.update(is_active=True, last_login_time=datetime.now(), user_agent=ua, token=token, open_id=open_id)
        return "OK"

    @classmethod
    def check_upsert_all(cls):
        """登陆所有账号"""
        now = datetime.now()
        current_app.logger.info(">>>> start to login scqcp.com:")
        valid_cnt = 0
        has_checked = {}
        for bot in cls.objects:
            has_checked[bot.telephone] = 1
            if bot.telephone not in SCQCP_ACCOUNTS:
                bot.update(is_active=False)
                continue
            pwd, is_encrypt = SCQCP_ACCOUNTS[bot.telephone]
            bot.update(password=pwd, is_encrypt=is_encrypt)

            # 近5天之内登陆的先不管
            if bot.is_active and (bot.last_login_time-now).seconds < 5*24*3600:
                valid_cnt += 1
                continue

            if bot.relogin() == "OK":
                valid_cnt += 1

        for tele, (pwd, is_encrypt) in SCQCP_ACCOUNTS.items():
            if tele in has_checked:
                continue
            bot = cls(is_active=False,
                      telephone=tele,
                      password=pwd,
                      is_encrypt=is_encrypt)
            bot .save()
            if bot.relogin() == "OK":
                valid_cnt += 1
        current_app.logger.info(">>>> end login scqcp.com, success %d", valid_cnt)
