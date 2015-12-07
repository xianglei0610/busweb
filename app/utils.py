# -*- coding:utf-8 -*-
import hashlib
from PIL import Image
import pytesseract

import cStringIO
import urllib2

def md5(msg):
    md5 = hashlib.md5(msg.encode('utf-8')).hexdigest()
    return md5
