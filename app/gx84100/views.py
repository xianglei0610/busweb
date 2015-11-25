# -*- coding:utf-8 -*-

# from app.gx84100 import gx84100

import requests

# @gx84100.route('/', methods=['GET', 'POST'])
# def index():
#     pass



# @gx84100.route('/getTrainInfo', methods=['GET', 'POST'])
def getTrainInfo():

    url = 'http://www.84100.com/getTrainInfo/ajax'
    payload = {
        "shiftId": 91730575 ,   
        "startId": 45010000 ,
        "startName": u"埌东站",    
        "ttsId": ''  
             }

    trainInfo = requests.post(url, data=payload)
    
    print trainInfo.json()
    
    
getTrainInfo()  