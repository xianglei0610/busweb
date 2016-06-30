# -*- coding:utf-8 -*-
import os
import hashlib
import redis
import random
import re
import cStringIO
from pypinyin import pinyin
import pypinyin
import requests
from time import sleep


try:
    import Image
    import ImageDraw
    import ImageFont
    import ImageFilter
except ImportError:
    from PIL import Image
    from PIL import ImageDraw
    from PIL import ImageFont
    from PIL import ImageFilter
from datetime import datetime as dte
from app import BASE_DIR
from flask import current_app
from pytesseract import image_to_string


_redis_pool_list = {}


def vcode_cqky(img_content):
    ims = cStringIO.StringIO(img_content)
    im = Image.open(ims)
    im = im.convert('L')
    im = im.point(lambda x: 255 if x > 140 else 0)
    im = ecp(im)
    code = image_to_string(im, lang='kp', config='-psm 8')
    return code


def vcode_scqcp(img_content):
    ims = cStringIO.StringIO(img_content)
    im = Image.open(ims)

    im = im.convert('L')
    im = im.point(lambda x: 255 if x > 160 else 0)
    im = ecp(im)
    code = image_to_string(im, lang='scqcp', config='-psm 8')
    return code


def vcode_zhw():
    url = 'http://www.zhwsbs.gov.cn:9013/jsps/shfw/checkCode.jsp'
    for x in xrange(5):
        r = requests.get(url)
        im = cStringIO.StringIO(r.content)
        im = Image.open(im)
        im = im.convert('L')
        im = im.point(lambda x: 255 if x > 130 else 0)
        im = ecp(im, 7)
        code = image_to_string(im, lang='zhw2', config='-psm 8')
        code = re.findall(r'[0-9a-zA-Z]', str(code))
        code = ''.join(code)
        if len(code) == 4:
            # im.save(code + '.png')
            return (code, r.cookies)
        sleep(0.25)


def trans_js_str(s):
    """
    {aa:'bb'} ==> {"aa":"bb"}
    """
    for k in set(re.findall("([A-Za-z]+):", s)):
        s= re.sub(r"\b%s\b" % k, '"%s"' % k, s)
    s = s.replace("'", '"')
    return s


def get_redis(name):
    if name not in _redis_pool_list:
        info = current_app.config["REDIS_SETTIGNS"][name]
        pool = redis.ConnectionPool(host=info["host"],
                                    port=info["port"],
                                    db=info["db"],
                                    socket_timeout=5)
        _redis_pool_list[name] = pool
    return redis.Redis(connection_pool=_redis_pool_list[name])


def weight_choice(weights):
    rnd = random.random() * sum(weights.values())
    for k, w in weights.items():
        rnd -= w
        if rnd < 0:
            return k


def idcard_birthday(idcard):
    return dte.strptime(idcard[6:14], "%Y%m%d")


def chinese_week_day(date):
    mapping = {
        0: "周一",
        1: "周二",
        2: "周三",
        3: "周四",
        4: "周五",
        5: "周六",
        6: "周日",
    }
    return mapping[date.weekday()]


def md5(msg):
    md5 = hashlib.md5(msg.encode('utf-8')).hexdigest()
    return md5


def sha1(msg):
    return hashlib.sha1(msg.encode('utf-8')).hexdigest()


def get_pinyin_first_litter(hanzi):
    pinyin_list = pinyin(hanzi, style=pypinyin.FIRST_LETTER)
    pinyin_st = ''
    for i in pinyin_list:
        pinyin_st += i[0]
    return pinyin_st


def getRedisObj(rdb=0):
    host = current_app.config["REDIS_HOST"]
    port = current_app.config["REDIS_PORT"]

    pool = redis.ConnectionPool(host=host,
                                port=port,
                                db=rdb,
                                socket_timeout=3)
    r = redis.Redis(connection_pool=pool)
    return r


numbers = ''.join(map(str, range(10)))
chars = ''.join((numbers))


def create_validate_code(size=(90, 30),
                         chars=chars,
                         mode="RGB",
                         bg_color=(255, 255, 255),
                         fg_color=(255, 0, 0),
                         font_size=18,
                         font_type=os.path.join(BASE_DIR, "res/Monaco.ttf"),
                         length=4,
                         draw_points=True,
                         point_chance = 2):
    '''''
    size: 图片的大小，格式（宽，高），默认为(120, 30)
    chars: 允许的字符集合，格式字符串
    mode: 图片模式，默认为RGB
    bg_color: 背景颜色，默认为白色
    fg_color: 前景色，验证码字符颜色
    font_size: 验证码字体大小
    font_type: 验证码字体，默认为 Monaco.ttf
    length: 验证码字符个数
    draw_points: 是否画干扰点
    point_chance: 干扰点出现的概率，大小范围[0, 50]
    '''
    width, height = size
    img = Image.new(mode, size, bg_color)   # 创建图形
    draw = ImageDraw.Draw(img)              # 创建画笔

    def get_chars():
        '''''生成给定长度的字符串，返回列表格式'''
        return random.sample(chars, length)

    def create_points():
        '''''绘制干扰点'''
        chance = min(50, max(0, int(point_chance)))     # 大小限制在[0, 50]

        for w in xrange(width):
            for h in xrange(height):
                tmp = random.randint(0, 50)
                if tmp > 50 - chance:
                    draw.point((w, h), fill=(0, 0, 0))

    def create_strs():
        '''''绘制验证码字符'''
        c_chars = get_chars()
        strs = '%s' % ''.join(c_chars)

        font = ImageFont.truetype(font_type, font_size)
        font_width, font_height = font.getsize(strs)

        draw.text(((width - font_width) / 3, (height - font_height) / 4),
                    strs, font=font, fill=fg_color)

        return strs

    if draw_points:
        create_points()
    strs = create_strs()

    # 图形扭曲参数
    params = [1 - float(random.randint(1, 2)) / 100,
              0,
              0,
              0,
              1 - float(random.randint(1, 10)) / 100,
              float(random.randint(1, 2)) / 500,
              0.001,
              float(random.randint(1, 2)) / 500
              ]
    img = img.transform(size, Image.PERSPECTIVE, params)    # 创建扭曲
    img = img.filter(ImageFilter.EDGE_ENHANCE_MORE)         # 滤镜，边界加强（阈值更大）
    return img, strs


def ecp(im, n=6):
    frame = im.load()
    (w, h) = im.size
    for i in xrange(w):
        for j in xrange(h):
            if frame[i, j] != 255:
                count = 0
                try:
                    if frame[i, j - 1] == 255:
                        count += 1
                except IndexError:
                    pass
                try:
                    if frame[i, j + 1] == 255:
                        count += 1
                except IndexError:
                    pass
                try:
                    if frame[i - 1, j - 1] == 255:
                        count += 1
                except IndexError:
                    pass
                try:
                    if frame[i - 1, j] == 255:
                        count += 1
                except IndexError:
                    pass
                try:
                    if frame[i - 1, j + 1] == 255:
                        count += 1
                except IndexError:
                    pass
                try:
                    if frame[i + 1, j - 1] == 255:
                        count += 1
                except IndexError:
                    pass
                try:
                    if frame[i + 1, j] == 255:
                        count += 1
                except IndexError:
                    pass
                try:
                    if frame[i + 1, j + 1] == 255:
                        count += 1
                except IndexError:
                    pass
                if count >= n:
                    frame[i, j] = 255
    return im
