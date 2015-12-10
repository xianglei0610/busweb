# -*- coding:utf-8 -*-

# 四川汽车票务网登陆账号
SCQCP_ACCOUNTS = {
    # telephone: {password, is_encrypt)
    #"15575101324": ("sha1$dae47$3702fcfa2d29e01350e98f0fe4057b8921c9d3d4", 1),
    "15575101324": ("cibRpL", 0),
}

SCQCP_DOMAIN = "http://java.cdqcp.com"


GX84100_DOMAIN = "http://wap.84100.com"

# 广西84100登陆账号
GX84100_ACCOUNTS = {
    # telephone: {password, opendid)
    "13267109876": ("123456", 'o82gDszqOaOk1_tdc54xQo4oGaLQ'),
}


BROWSER_USER_AGENT = [
    "Mozilla/5.0 (Windows NT 6.1; WOW64) AppleWebKit/537.1 (KHTML, like Gecko) Chrome/22.0.1207.1 Safari/537.1",
    "Mozilla/5.0 (Windows NT 6.1; WOW64) AppleWebKit/536.6 (KHTML, like Gecko) Chrome/20.0.1092.0 Safari/536.6",
    "Mozilla/5.0 (Windows NT 6.2) AppleWebKit/536.6 (KHTML, like Gecko) Chrome/20.0.1090.0 Safari/536.6",
    "Mozilla/5.0 (Windows NT 6.2; WOW64) AppleWebKit/537.1 (KHTML, like Gecko) Chrome/19.77.34.5 Safari/537.1",
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/536.5 (KHTML, like Gecko) Chrome/19.0.1084.9 Safari/536.5",
    "Mozilla/5.0 (Windows NT 6.0) AppleWebKit/536.5 (KHTML, like Gecko) Chrome/19.0.1084.36 Safari/536.5",
    "Mozilla/5.0 (Windows NT 6.1; WOW64) AppleWebKit/536.3 (KHTML, like Gecko) Chrome/19.0.1063.0 Safari/536.3",
    "Mozilla/5.0 (Windows NT 5.1) AppleWebKit/536.3 (KHTML, like Gecko) Chrome/19.0.1063.0 Safari/536.3",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_8_0) AppleWebKit/536.3 (KHTML, like Gecko) Chrome/19.0.1063.0 Safari/536.3",
    "Mozilla/5.0 (Windows NT 6.2) AppleWebKit/536.3 (KHTML, like Gecko) Chrome/19.0.1062.0 Safari/536.3",
    "Mozilla/5.0 (Windows NT 6.1; WOW64) AppleWebKit/536.3 (KHTML, like Gecko) Chrome/19.0.1062.0 Safari/536.3",
    "Mozilla/5.0 (Windows NT 6.2) AppleWebKit/536.3 (KHTML, like Gecko) Chrome/19.0.1061.1 Safari/536.3",
    "Mozilla/5.0 (Windows NT 6.1; WOW64) AppleWebKit/536.3 (KHTML, like Gecko) Chrome/19.0.1061.1 Safari/536.3",
    "Mozilla/5.0 (Windows NT 6.1) AppleWebKit/536.3 (KHTML, like Gecko) Chrome/19.0.1061.1 Safari/536.3",
    "Mozilla/5.0 (Windows NT 6.2) AppleWebKit/536.3  (KHTML, like Gecko) Chrome/19.0.1061.0 Safari/536.3",
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/535.24 (KHTML, like Gecko) Chrome/19.0.1055.1 Safari/535.24",
    "Mozilla/5.0 (Windows NT 6.2; WOW64) AppleWebKit/535.24 (KHTML, like Gecko) Chrome/19.0.1055.1 Safari/535.24",
]

MOBILE_USER_AGENG = [
    "Mozilla/5.0 (Linux; U; Android 4.0.3; ko-kr; LG-L160L Build/IML74K) AppleWebkit/534.30 (KHTML, like Gecko) Version/4.0 Mobile Safari/534.30",
    "Mozilla/5.0 (Linux; U; Android 4.0.3; de-ch; HTC Sensation Build/IML74K) AppleWebKit/534.30 (KHTML, like Gecko) Version/4.0 Mobile Safari/534.30",
    "Mozilla/5.0 (Linux; U; Android 2.3; en-us) AppleWebKit/999+ (KHTML, like Gecko) Safari/999.9",
    "Mozilla/5.0 (Linux; U; Android 2.3.5; zh-cn; HTC_IncredibleS_S710e Build/GRJ90) AppleWebKit/533.1 (KHTML, like Gecko) Version/4.0 Mobile Safari/533.1",
    "Mozilla/5.0 (Linux; U; Android 2.3.5; en-us; HTC Vision Build/GRI40) AppleWebKit/533.1 (KHTML, like Gecko) Version/4.0 Mobile Safari/533.1",
    "Dalvik/1.6.0 (Linux; U; Android 4.4.4; MI 4W MIUI/V7.0.5.0.KXDCNCI)",
]

# 爬取来源
SOURCE_SCQCP = "scqcp"
SOURCE_BUS100 = "gx84100"

SOURCE_MSG = {
    SOURCE_SCQCP: "四川汽车票务网",
    SOURCE_BUS100: "巴士壹佰",
}

# 订单状态
STATUS_FAIL = 0         # 失败
STATUS_SUCC = 1         # 成功
STATUS_ISSUE_DOING = 2  # 正在出票
STATUS_LOCK = 3         # 锁票成功
STATUS_COMMIT = 4       # 提交订单(初始状态)
STATUS_LOCK_FAIL = 5    # 锁票失败
STATUS_GIVE_BACK = 6    # 以退票
STATUS_TIMEOUT = 8     # 订单过期
STATUS_ISSUE_FAIL = 13  # 出票失败
STATUS_ISSUE_OK = 14    # 出票成功

STATUS_MSG = {
    STATUS_FAIL:  "订单失败",
    STATUS_SUCC:  "订单完成",
    STATUS_ISSUE_DOING: "正在出票",
    STATUS_LOCK: "锁票成功",
    STATUS_COMMIT: "订单提交",
    STATUS_LOCK_FAIL: "锁票失败",
    STATUS_ISSUE_FAIL: "出票失败",
    STATUS_ISSUE_OK: "出票成功",
    STATUS_GIVE_BACK: "已退票",
    STATUS_TIMEOUT: "订单过期",
}

# 证件类型
IDTYPE_IDCARD = 1   # 身份证

# 乘客类型
RIDER_ADULT = 1     # 成人
RIDER_CHILD = 0     # 儿童

# 通用状态码
RET_OK = 1
RET_PARAM_ERROR = 2     # 参数错误
RET_SERVER_ERROR = 3    # 服务器异常
RET_PAGE_404 = 4        # 404

# 订单错误1xx
RET_ORDER_404 = 101     # 订单不存在
# 线路错误2xx
RET_LINE_404 = 201      # 线路不存在


