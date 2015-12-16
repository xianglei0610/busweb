# -*- coding:utf-8 -*-
import hashlib
import redis
from app.constants import REDIS_HOST, REDIS_PASSWD


def md5(msg):
    md5 = hashlib.md5(msg.encode('utf-8')).hexdigest()
    return md5


def getRedisObj(rdb=0, host=None, password=None):
    if host is None:
        host = REDIS_HOST
    if password is None:
        password = REDIS_PASSWD

    pool = redis.ConnectionPool(
            host=host, password=password, port=6379, db=rdb, socket_timeout=3)
    r = redis.Redis(connection_pool=pool)
    return r


