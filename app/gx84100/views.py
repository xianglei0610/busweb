# -*- coding:utf-8 -*-

# from app.gx84100 import gx84100
from lxml import etree
import requests

# @gx84100.route('/', methods=['GET', 'POST'])
# def index():
#     pass



# @gx84100.route('/getTrainInfo', methods=['GET', 'POST'])
def getTrainInfo():

    url = 'http://www.84100.com/getTrainInfo/ajax'
    payload = {
        "shiftId": 92069979 ,   
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
        
    
# getTrainInfo()  





def test():
    
    
    
    headers={"cookie":'JSESSIONID=21CB50BE34B16A49661D21F0C1E85660'} 
    
    
    
    
    r = requests.get('http://www.84100.com/user/getPeople/ajax?id=171715', headers=headers)  #huoqulianxirenxiangqing
    #r = requests.get('http://www.84100.com/user/getPeople/ajax?id=171715')
    
    

    content = r.content
    print content


test()

def xiadan():
    
    
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
    pass
