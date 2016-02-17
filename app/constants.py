# -*- coding:utf-8 -*-
# 客户端类型
CLIENT_WEB = "web"          # pc网站
CLIENT_WAP = "wap"          # wap网
CLIENT_APP = "app"          # 移动端

# 爬取来源
SOURCE_SCQCP = "scqcp"
SOURCE_BUS100 = "bus100"
SOURCE_CTRIP = "ctrip"
SOURCE_CBD = "cbd"
SOURCE_JSKY = "jsky"
SOURCE_BABA = "baba"
SOURCE_TC = "tongcheng"

SOURCE_INFO = {
    SOURCE_SCQCP: {
        "name": "四川汽车票务网",
        "website": "www.scqcp.com",
        "accounts": {
            # telephone: {password, is_encrypt)
            "13267109876": ("123456", 0),      # 用于本地测试
            # "15575101324": ("cibRpL", 0),
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
            "13760232870": ("a112308", '1'),
            "18588468517": ("lxy12308", '1'),
            "15626025673": ("lxy12308", '1'),

            "17095467255": ("123456", '1'),
            "13087921341": ("123456", '1'),
            "13291407375": ("123456", '1'),
            "15574335669": ("123456", '1'),
            "15577963124": ("123456", '1'),
            "13058794526": ("123456", '1'),
            "13760160877": ("123456", '1'),
            "15677383224": ("123456", '1'),
            "13065682174": ("123456", '1'),
            "15676700545": ("123456", '1'),
            "13185698464": ("123456", '1'),
            "15999668312": ("123456", '1'),
            "18719051278": ("123456", '1'),
            "15914167537": ("123456", '1'),
            "15115596871": ("123456", '1'),
            "13450027307": ("123456", '1'),
            "18719031096": ("123456", '1'),
            "13424384754": ("123456", '1'),
            "18826550827": ("123456", '1'),
            "13040802607": ("123456", '1'),
            "18656022990": ("123456", '1'),
            "18673582690": ("123456", '1'),
            "13428974866": ("123456", '1'),
            "15112625120": ("123456", '1'),
            "13417384977": ("123456", '1'),
            "15986844790": ("123456", '1'),
            "13510175093": ("123456", '1'),
        }
    },
    SOURCE_CTRIP: {
        "name": "携程网",
        "website": "www.ctrip.com",
        "accounts": {
            # telephone: {password, auth)
            #"15575101324": ("icbRpL", ''),
            "15626025673": ("lxy12308", ""),
            "15112257071": ("7996266", ""),
            "s89xhlnjkb@sina.com": ("cibRpL", ""),
            "hdsjd255596@sina.com": ("cibRpL", ""),
            "ereref1633@sina.com": ("cibRpL", ""),
            "sjso123@163.com": ("lxy12308", ""),
            "asadjd12@sina.com": ("lxy12308", ""),
            "s8vg43@sina.com": ("lxy12308", ""),
        }
    },
    SOURCE_CBD: {
        "name": "车巴达",
        "website": "www.chebada.com",
        "accounts": {
            "17095467255": ("123456", ""),
            "15999668312": ("123456", ""),
            "13760160877": ("123456", ""),
            "15999668312": ("123456", ""),

            #"15575101324": ("cibRpL", ''),      #

            ##"13267109876": ("123456", ""),

            #"13087921341": ("123456", ""),      # leilei
            #"13291407375": ("123456", ""),
            #"15676700545": ("123456", ""),
            #"15677383224": ("123456", ""),
            #"13040802607": ("123456", ""),      # 美晨
            #"13760438677": ("123456", ""),      # caiqiji

            #"13424384754": ("123456", ""),
            #"15311893089": ("123456", ""),
            #"18719031096": ("123456", ""),
            #"15112625120": ("123456", ""),
            #"18676665359": ("123456", ""),
            #"18719051278": ("123456", ""),
            #"13428974866": ("123456", ""),
            #"15914167537": ("123456", ""),
            #"13040802607": ("123456", ""),
            #"15574335669": ("123456", ""),
            #"18656022990": ("123456", ""),
            #"13560750217": ("123456", ""),
            #"18928929725": ("123456", ""),
            #"13417384977": ("123456", ""),
            #"13559267939": ("123456", ""),
            #"18673582690": ("123456", ""),
            #"15115596871": ("123456", ""),
            ## "18826550827": ("123456", ""),  # 未注册,账号异常
            #"18684920073": ("123456", ""),
            #"13450027307": ("123456", ""),
        }
    },
    SOURCE_JSKY: {
        "name": "江苏客运",
        "website": "www.jskylwsp.com",
        "accounts": {
            "15575101324": ("cibRpL", ''),
            "13185698464": ("123456", ""),
            "15676700545": ("123456", ""),
            "18588468517": ("123456", ""),
            "15577963124": ("123456", ""),
            "13058794526": ("123456", ""),
            "13760160877": ("123456", ""),
            "18575593355": ("123456", ""),
            "15818777287": ("123456", ""),

            #"13291407375": ("123456", ""),
            #"13087921341": ("123456", ""),
            #"13065682174": ("123456", ""),
            #"15677383224": ("123456", ""),
            #"15574335669": ("123456", ""),
        },
        "pwd_encode": {
            "cibRpL": "fQPjVx7bgVrG60XZH3fxQw==",
            "123456": "RH0iLaK7awGTnhWzWtWEaw==",
        }
    },
    SOURCE_BABA: {
        "name": "巴巴",
        "website": "http://www.bababus.com/",
        "accounts": {
            "15575101324": ("cibRpL", ''),
            "18575593355": ("123456", ""),
            "13559267939": ("123456", ""),
            "18719051278": ("123456", ""),
            "15914167537": ("123456", ""),
            "13040802607": ("123456", ""),
            "13267109876": ("123456", ""),
            "18928929725": ("123456", ""),
            "18719031096": ("123456", ""),
            "13510175093": ("123456", ""),
            "13424384754": ("123456", ""),
            "18219523231": ("123456", ""),
            "18656022990": ("123456", ""),
            "15112625120": ("123456", ""),
            "18673582690": ("123456", ""),
            "13560750217": ("123456", ""),
            "13450027307": ("123456", ""),
            "18826550827": ("123456", ""),
            "15311893089": ("123456", ""),
            "18588468517": ("123456", ""),
            "18684920073": ("123456", ""),
            "15574335669": ("123456", ""),
            "18673582670": ("123456", ""),
        },
    },
    SOURCE_TC: {
        "name": "同程",
        "website": "http://www.ly.com/",
        "accounts": {
            "15575101324": ("cibRpL0", ''),
        },
        "pwd_encode": {
            "cibRpL0": "d17bc469b36817893ff0cdae06b5422f",
        }
    },
}

SCQCP_DOMAIN = "http://java.cdqcp.com"
Bus100_DOMAIN = "http://wap.84100.com"

ADMINS = ['xiangleilei@12308.com', 'luojunping@12308.com']


sms_phone_list = ['13267109876','15575101324','18575593355']


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
    "Mozilla/5.0 (Linux; U; Android 4.0.3; zh-cn; LG-L160L Build/IML74K) AppleWebkit/534.30 (KHTML, like Gecko) Version/4.0 Mobile Safari/534.30",
    "Mozilla/5.0 (Linux; U; Android 4.0.3; zh-cn; HTC Sensation Build/IML74K) AppleWebKit/534.30 (KHTML, like Gecko) Version/4.0 Mobile Safari/534.30",
    "Mozilla/5.0 (Linux; U; Android 3.3; zh-cn) AppleWebKit/999+ (KHTML, like Gecko) Safari/999.9",
    "Mozilla/5.0 (Linux; U; Android 3.3.5; zh-cn; HTC_IncredibleS_S710e Build/GRJ90) AppleWebKit/533.1 (KHTML, like Gecko) Version/4.0 Mobile Safari/533.1",
    "Mozilla/5.0 (Linux; U; Android 3.3.5; zh-cn; HTC Vision Build/GRI40) AppleWebKit/533.1 (KHTML, like Gecko) Version/4.0 Mobile Safari/533.1",
    "Dalvik/1.6.0 (Linux; U; Android 4.4.4; MI 4W MIUI/V7.0.5.0.KXDCNCI)",
]


STATUS_WAITING_ISSUE = 3    # 等待出票, 在源网站锁票成功
STATUS_WAITING_LOCK = 4     # 等待下单，12308已提交了订单，但未向源网站提交订单
STATUS_LOCK_FAIL = 5        # 下单失败，12308已提交了订单，向源网站提交订单失败
STATUS_GIVE_BACK = 6        # 退票
STATUS_LOCK_RETRY = 7       # 锁票重试
STATUS_ISSUE_ING = 12       # 源站正在出票
STATUS_ISSUE_FAIL = 13      # 出票失败, 支付完成后，已确认源网站出票失败
STATUS_ISSUE_SUCC = 14      # 出票成功, 支付完成后，源网站也出票成功

STATUS_MSG = {
    STATUS_WAITING_ISSUE: "等待出票",
    STATUS_WAITING_LOCK: "等待下单",
    STATUS_ISSUE_FAIL: "出票失败",
    STATUS_LOCK_FAIL: "下单失败",
    STATUS_ISSUE_SUCC: "出票成功",
    STATUS_GIVE_BACK: "已退款",
    STATUS_ISSUE_ING: "正在出票",
    STATUS_LOCK_RETRY: "下单重试",
}


# 支付状态
PAY_STATUS_NONE = 0          # 未知
PAY_STATUS_UNPAID = 1        # 未支付
PAY_STATUS_PAID = 2          # 已支付
PAY_STATUS_REFUND = 3        # 已退款

PAY_STATUS_MSG = {
    PAY_STATUS_UNPAID: "未支付",
    PAY_STATUS_NONE: "未知",
    PAY_STATUS_PAID: "已支付",
    PAY_STATUS_REFUND: "已退款",
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
RET_CITY_NOT_OPEN = 203     # 该城市未开放

# 立即支付按钮变灰持续时间
PAY_CLICK_EXPIR = 30

ISSUE_FAIL_WARNING = 3
ISSUEING_WARNING = 3

# redis keys
LAST_PAY_CLICK_TIME = "payclicktime:%s"
ACCOUNT_ORDER_COUNT = "account_order_count"
CURRENT_ACCOUNT = "current_account"
RK_ISSUE_FAIL_COUNT = "%s_issue_fail"
RK_ISSUEING_COUNT = "issueing_count"

RK_WATING_LOCK_ORDERS = "wating_lock_orders"       # 等待下单的订单
RK_DEALING_ORDERS = "dealing_orders:%s"            # 客服正在处理的订单

# 短信模版

DUAN_XIN_TEMPL = {
    SOURCE_SCQCP: "您已购买%(time)s%(start)s至%(end)s的汽车票%(amount)s张，取票验证码%(code)s，请在发车时间前乘车",
    SOURCE_BUS100: "温馨提醒：您有%(amount)s张汽车票，出发日期：%(time)s；行程：%(start)s-%(end)s；订单号：%(order)s；%(ticketPassword)s请在发车前两小时内凭乘车人身份证取票。祝您旅途愉快！",
    SOURCE_CTRIP: "%(time)s，%(start)s--%(end)s 共%(amount)s张成功出票。取票验证码%(code)s，请在发车时间前乘车",
    SOURCE_CBD: "车站订单号：%(raw_order)s,发车时间：%(time)s,%(start)s-%(end)s,请至少提前半小时(节假日请提前一小时以上)至乘车站凭取票号(%(no)s)、取票密码(%(code)s)或身份证、车站订单号取票,如需改签、退票请前往始发客运站按规定办理。",
    SOURCE_BABA: "购票成功,取票号:%(no)s,密码:%(code)s,取票点:%(site)s,(%(start)s-%(end)s %(time)s),请旅客尽早到车站取票.",
}

WEIGHTS = {
    SOURCE_CBD: 200,
    SOURCE_JSKY: 800,

    SOURCE_CTRIP: 500,
    SOURCE_SCQCP: 500,

    SOURCE_BUS100: 1000,
}
