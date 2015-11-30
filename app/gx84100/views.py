# -*- coding:utf-8 -*-

# from app.gx84100 import gx84100
from lxml import etree
import requests
import re 
import json

# @gx84100.route('/', methods=['GET', 'POST'])
# def index():
#     pass



# @gx84100.route('/getTrainInfo', methods=['GET', 'POST'])
def getTrainInfoYuPiaofromPC():
    """
    余票
    """
    url = 'http://www.84100.com/getTrainInfo/ajax'
    payload = {
        "shiftId": 93079946 ,   
        "startId": 45010000 ,
        "startName": u"埌东站",    
        "ttsId": ''  
             }

    trainInfo = requests.post(url, data=payload)
    trainInfo = trainInfo.json()
    yupiao=0
    if str(trainInfo['flag'])=='0':
        sel = etree.HTML(trainInfo['msg'])
        yupiao= sel.xpath('//div[@class="ticketPrice"]/ul/li/strong[@id="leftSeatNum"]/text()')
        if yupiao:
            yupiao = int(yupiao[0])
    
# getTrainInfoYuPiaofromPC()  





def createOrderFromPC():
    
    headers={"cookie":'CNZZDATA1254030256=1424378201-1448438538-http%253A%252F%252Fwww.84100.com%252F%7C1448444026; JSESSIONID=88147ED689FD77E2ADA4D2B553FF1E36'} 
    
    r = requests.get('http://www.84100.com/user/getPeople/ajax?id=171715', headers=headers)  #huoqulianxirenxiangqing
    

    content = r.content
    print content


    # startId    45010003
    # name    向磊磊
    # mobile    13267109876
    # planId    92118664
    # ticketNo    
    # ticketPassword    
    # idTypes    1,1
    # idNos    429006199012280042,429006198906100034
    # names    李梦蝶,向磊磊
    # mobiles    ,
    # ticketTypes    全票,全票
    
    
    url = 'http://www.84100.com/createOrder/ajax'
    payload = {
        "startId": 45010000 ,
        "name": u"向磊磊",
        "mobile":"13267109876",
        
        "planId": 93079871 ,   
        "ticketNo":'',
        "ticketPassword": '',
        "idTypes":"1,1",
        "idNos" : "429006199012280042,429006198906100034",
        "names" : u"李梦蝶,向磊磊",
        "mobiles": "",    
        "ticketTypes": u"全票,全票"  
        }

    orderInfo = requests.post(url, data=payload,headers=headers)
    
    print orderInfo.json()
    
# createOrderFromPC()


def queryTicketPasswdFromPC():
    
    url="http://www.84100.com/orders.shtml"
    
    headers={"cookie":'Cookie: Cookie: CNZZDATA1254030256=1424378201-1448438538-http%253A%252F%252Fwww.84100.com%252F%7C1448444026; JSESSIONID=3798865869AAB17AFF58752C57F24CA1; trainHistory=%5B%7B%22sendDate%22%3A%222015-11-27%22%2C%22startId%22%3A%2245010000%22%2C%22startName%22%3A%22%E5%9F%8C%E4%B8%9C%E7%AB%99%22%2C%22endName%22%3A%22%E5%AE%9D%E5%AE%89%22%2C%22showDate%22%3Anull%2C%22showWeek%22%3A%22%E6%98%9F%E6%9C%9F%E4%BA%94%22%2C%22createDate%22%3A%222015-11-27+09%3A38%3A28%22%7D%5D'} 
    
    r = requests.get(url, headers=headers) 
    res = r.content

#     print type(res)
#     
#     sel = etree.HTML(r.content)
    
#     orders=sel.xpath('/html/body/div[2]/div[2]/div[3]')
#     for i in orders:
#         print i
#         print '22222222222', i.xpath('table')
    
    
#     b= re.findall(r'<td width="100" rowspan="1" class="merge">(.*)orderId="151126112013007890',res)
#     
#     
    matchObj = re.findall( r'151126112013007890(.*)orderId="151126112013007890"', res, re.S)
    print matchObj
    a = matchObj[0].replace('\r\n','').replace(' ','')
#     matchObj1 = re.search( r'<strong>(.*)￥(.*)orderId="151126112013007890"', a, re.S)
#     print matchObj1
#     b= matchObj1.group()
    
    matchObj2 = re.findall( r'<tdwidth="80"rowspan="1"class="merge">(.*)</td><tdwidth="100"', a, re.M)
    print  matchObj2
# queryTicketPasswdFromPC()



def queryOrderStatusFromPC():
    
    url = "http://www.84100.com/orderInfo.shtml"
    
    headers={"cookie":'Cookie: Cookie: CNZZDATA1254030256=1424378201-1448438538-http%253A%252F%252Fwww.84100.com%252F%7C1448444026; JSESSIONID=3798865869AAB17AFF58752C57F24CA1; trainHistory=%5B%7B%22sendDate%22%3A%222015-11-27%22%2C%22startId%22%3A%2245010000%22%2C%22startName%22%3A%22%E5%9F%8C%E4%B8%9C%E7%AB%99%22%2C%22endName%22%3A%22%E5%AE%9D%E5%AE%89%22%2C%22showDate%22%3Anull%2C%22showWeek%22%3A%22%E6%98%9F%E6%9C%9F%E4%BA%94%22%2C%22createDate%22%3A%222015-11-27+09%3A38%3A28%22%7D%5D'} 
    
    data={
          "orderId":"151127113905016034"
          }
    
    r = requests.post(url, data=data ,headers=headers) 
#     print r.content


    sel = etree.HTML(r.content)
    a = sel.xpath('//div[@class="order-details"]/ul')
    for  i in  a:
        print i.xpath('li')[1].xpath('em/text()')[0].replace('\r\n','').replace(' ','') 
    
queryOrderStatusFromPC()





def LoginFromWap():

    url= 'http://wap.84100.com/wap/login/ajaxLogin.do'
    
    data={
          "mobile" :  13267109876,
          "password" : 123456,
          "phone" :   '' ,
          "code"  :  '' 
    }
    
    r = requests.post(url, data=data)  
    _cookies = r.cookies

    status = {
    "1":"未支付",
    "2":'出票中',
    "3":"订票成功",
    "4":"交易关闭"
     }
    
    query_order_list_url ='http://wap.84100.com/wap/userCenter/ticketOrders.do'
    
    r = requests.get(query_order_list_url, cookies=_cookies) 
    
    sel = etree.HTML(r.content)
    a = sel.xpath('//div[@id="orderJson"]/text()')[0]
    
    b=json.loads(a)
    order_list = b['pageData']
    
#LoginFromWap()