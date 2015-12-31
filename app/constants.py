# -*- coding:utf-8 -*-

# 爬取来源
SOURCE_SCQCP = "scqcp"
SOURCE_BUS100 = "bus100"
SOURCE_CTRIP = "ctrip"

SOURCE_INFO = {
    SOURCE_SCQCP: {
        "name": "四川汽车票务网",
        "website": "www.scqcp.com",
        "accounts": {
            # telephone: {password, is_encrypt)
            # "13267109876": ("123456", 0),      # 用于本地测试
            "15575101324": ("cibRpL", 0),
            "15626025673": ("lxy12308", 0),
            "13719074050": ("lxy12308", 0),
            "18676665359": ("lxy12308", 0),
            "18219523231": ("lxy12308", 0),
            "13559267939": ("lxy12308", 0),
            "13424384754": ("lxy12308", 0),
            "13560750217": ("lxy12308", 0),
            "18656022990": ("lxy12308", 0),
            "15914162537": ("lxy12308", 0),
            "13510175093": ("lxy12308", 0),
        }
    },
    SOURCE_BUS100: {
        "name": "巴士壹佰",
        "website": "www.84100.com",
        "accounts": {
            # telephone: {password, opendid)
            "13267109876": ("123456", '7pUGyHIri3Fjk6jEUsvv4pNfBDiX1448953063894'),
            "15575101324": ("icbRpL", 'o82gDszqOaOk1_tdc54xQo4oGaL1'),
        }
    },
    SOURCE_CTRIP: {
        "name": "携程网",
        "website": "www.ctrip.com",
        "accounts": {
            # telephone: {password, auth)
            "15575101324": ("icbRpL", ''),
        }
    }
}

CTRIP_HEADS = {
    "15575101324": {
        "cid": "09031120210146050165",
        "ctok": "",
        "cver": "1.0",
        "lang": "01",
        "sid": "8888",
        "syscode": "09",
        "auth": "310AB1B95E0DB5DFD369286D8AA5B5D9586D71FD8D9B5B6653C140503EDE8F0F",
        "sauth": "3CA2CAF81E580E6DFFEB80141AA84700FCFFAF1F1BED587A7BFC5736E6E89CDE"
    },
    "15626025673": {
        "cid": "09031120210146050165",
        "ctok": "",
        "cver": "1.0",
        "lang": "01",
        "sid": "8888",
        "syscode": "09",
        "auth": "661CD5CAFCE6FA37467AB055B9B5241FDB73AD9A59F8033A50F270E5CF608F98",
        "sauth": "D272C7D76CB9EC7DC34C2D823B4AC09AB3FF514F541B829D6BD9C27A887D40AC"
    },
    "15112257071": {
        "cid": "09031120210146050165",
        "ctok": "",
        "cver": "1.0",
        "lang": "01",
        "sid": "8888",
        "syscode": "09",
        "auth": "661CD5CAFCE6FA37467AB055B9B5241FDB73AD9A59F8033A50F270E5CF608F98",
        "sauth": "D272C7D76CB9EC7DC34C2D823B4AC09AB3FF514F541B829D6BD9C27A887D40AC"
    }
}

SCQCP_DOMAIN = "http://java.cdqcp.com"
Bus100_DOMAIN = "http://wap.84100.com"

ADMINS = ['xiangleilei@12308.com','luojunping@12308.com']

REDIS_HOST = '127.0.0.1'
REDIS_PASSWD = ""
REDIS_PORT = 6379
KF_ORDER_CT = 3

TOKEN = '303fed16373c61a9ee8bdc27f9b6ca4e' #代购token

HOST = 'http://sdk.open.api.igexin.com/apiex.htm'
AppID = "BRAvWtfxoz6Fvc4HaXciy"
AppKey = "mHFHq6gxrm6E2lEMvXQpIA"
AppSecret = "hNkmc4rFI69G6c5vT4lIL"
MasterSecret = "9lDpT4uieS6qM57euqOFN1"


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


STATUS_WAITING_ISSUE = 3    # 等待出票, 在源网站锁票成功
STATUS_WAITING_LOCK = 4     # 等待下单，12308已提交了订单，但未向源网站提交订单
STATUS_LOCK_FAIL = 5        # 下单失败，12308已提交了订单，向源网站提交订单失败
STATUS_GIVE_BACK = 6        # 退票
STATUS_ISSUE_FAIL = 13      # 出票失败, 支付完成后，已确认源网站出票失败
STATUS_ISSUE_SUCC = 14      # 出票成功, 支付完成后，源网站也出票成功

STATUS_MSG = {
    STATUS_WAITING_ISSUE: "等待出票",
    STATUS_WAITING_LOCK: "等待下单",
    STATUS_ISSUE_FAIL: "出票失败",
    STATUS_LOCK_FAIL: "下单失败",
    STATUS_ISSUE_SUCC: "出票成功",
    STATUS_GIVE_BACK: "已退票",
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
RET_ORDER_404 = 101         # 订单不存在
RET_LOCK_FAIL = 102         # 锁票失败
RET_ISSUED_FAIL = 103       # 出票失败
RET_PRICE_WRONG = 104       # 金额不对

# 线路错误2xx
RET_LINE_404 = 201          # 线路不存在
RET_BUY_TIME_ERROR = 202    # 线路不在预售期

# 立即支付按钮变灰持续时间
# 8s
PAY_CLICK_EXPIR = 4

# redis keys
LAST_PAY_CLICK_TIME = "payclicktime:%s"
ACCOUNT_ORDER_COUNT = "account_order_count"
CURRENT_ACCOUNT = "current_account"


# 源站选择
SOURCE_MAPPING = {
    "成都": SOURCE_CTRIP,
    "成都市": SOURCE_CTRIP,
}
