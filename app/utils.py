# -*- coding:utf-8 -*-
import hashlib
from PIL import Image
import pytesseract

import cStringIO
import urllib2


def md5(msg):
    md5 = hashlib.md5(msg.encode('utf-8')).hexdigest()
    return md5


def recognize_img_code(url):
    """
    安装依赖
    ubuntu下:
        sudo pip install pytesseract
        sudo apt-get install tesseract-ocr
    """
    file = urllib2.urlopen(url)
    tmpIm = cStringIO.StringIO(file.read())
    im = Image.open(tmpIm)
    return pytesseract.image_to_string(im)
