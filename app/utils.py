# -*- coding:utf-8 -*-
import hashlib


def md5(msg):
    md5 = hashlib.md5(msg.encode('utf-8')).hexdigest()
    return md5
