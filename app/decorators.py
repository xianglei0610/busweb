# -*- coding:utf-8 -*-
import threading


def async(func):
    def _wrap(*args, **kwargs):
        t = threading.Thread(target=func, *args, **kwargs)
        t.start()
    return _wrap
