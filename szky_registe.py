#!/usr/bin/env python
# encoding: utf-8
import os
import random
import datetime
import requests
import re
import urllib
from datetime import date, timedelta
from bs4 import BeautifulSoup
from app.utils import vcode_cqky
from app import kefu_log

BASE_DIR = os.path.dirname(os.path.dirname(__file__))
DC_PATH = BASE_DIR + "districtcode.txt"

form_url = "http://211.162.125.225/User/Register.aspx"
headers = {
    "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_10_5) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/48.0.2564.116 Safari/537.36",
}

# 随机生成手机号码
def createPhone():
  prelist=["130","131","132","133","134","135","136","137","138","139","147","150","151","152","153","155","156","157","158","159","186","187","188"]
  return random.choice(prelist)+"".join(random.choice("0123456789") for i in range(8))

def createIDCard():
    def getdistrictcode():
        with open(DC_PATH) as file:
            data = file.read()
            districtlist = data.split('\n')
        for node in districtlist:
            if node[10:11] != ' ':
                state = node[10:].strip()
            if node[10:11]==' 'and node[12:13]!=' ':
                city = node[12:].strip()
            if node[10:11] == ' 'and node[12:13]==' ':
                district = node[14:].strip()
                code = node[0:6]
                codelist.append({"state":state,"city":city,"district":district,"code":code})
    global codelist
    codelist = []
    if not codelist:
        getdistrictcode()
    id = codelist[random.randint(0,len(codelist))]['code'] #地区项
    id = id + str(random.randint(1930,2013)) #年份项
    da = date.today()+timedelta(days=random.randint(1,366)) #月份和日期项
    id = id + da.strftime('%m%d')
    id = id+ str(random.randint(100,300))#，顺序号简单处理
    i = 0
    count = 0
    weight = [7, 9, 10, 5, 8, 4, 2, 1, 6, 3, 7, 9, 10, 5, 8, 4, 2] #权重项
    checkcode ={'0':'1','1':'0','2':'X','3':'9','4':'8','5':'7','6':'6','7':'5','8':'5','9':'3','10':'2'} #校验码映射
    for i in range(0,len(id)):
        count = count +int(id[i])*weight[i]
        id = id + checkcode[str(count%11)] #算出校验码
        return id


def createEmail():
    s = ""
    for i in range(random.randint(3, 6)):
        s+=chr(random.randint(0, 26) + 97)
    s += str(random.randint(1000, 99999))

    prefix = random.choice(["qq", "163", "126", "foxmail", "gmail", "sina"])
    return s + "@" + prefix + ".com"


def registe(nickname, name, idcard, phone):
    r = requests.get(form_url, headers=headers)
    cookies = dict(r.cookies)
    soup = BeautifulSoup(r.content, "lxml")
    params = {}
    for e in soup.findAll("input"):
        params[e.get("name")] = e.get("value")
    nickname = 'a'+phone
    params["ctl00$FartherMain$txt_Code"] = nickname
    params["ctl00$FartherMain$txt_Password"] = "123456"
    params["ctl00$FartherMain$txt_Password2"] = "123456"
    params["ctl00$FartherMain$txt_Name"] = name
    params["ctl00$FartherMain$Sex"] = random.choice(['rbt_SexM', 'bt_SexS'])
    params["ctl00$FartherMain$ddl_IDtype"] = 1
    params["ctl00$FartherMain$txt_IDCode"] = ''
    params["ctl00$FartherMain$txt_Mobile"] = ''
    params["ctl00$FartherMain$txtQQ"] = ''
    params["ctl00$FartherMain$txt_Telephone"] = ''
    params["ctl00$FartherMain$txt_Email"] = ''
    params["ctl00$FartherMain$txt_Postcode"] = ''
    params["ctl00$FartherMain$txt_Address"] = ''
    params["ctl00$FartherMain$cbIsAgree"] = 'on'
    
    
    
    code_url = "http://211.162.125.225/ValidateCode.aspx?"
    r = requests.get(code_url, headers=headers, cookies=cookies)
    code = vcode_cqky(r.content)
    # local_filename = "/Users/luocky/Downloads/4.gif"
    # with open(local_filename, 'wb') as f:
    #     for chunk in r.iter_content(chunk_size=1024):
    #         if chunk:
    #             f.write(chunk)
    #             f.flush()
    # code = raw_input("valid_code%s:" % i)
    params["ctl00$FartherMain$txtVI"] = code
    
    headers["User-Agent"] = "Mozilla/5.0 (Windows NT 6.1; WOW64; rv:47.0) Gecko/20100101 Firefox/47.0"
    headers["Content-Type"] = "application/x-www-form-urlencoded"
    headers["Referer"] = "http://211.162.125.225/User/Register.aspx"

    r = requests.post("http://211.162.125.225/User/Register.aspx", headers=headers, data=urllib.urlencode(params), cookies=cookies)
    msg_lst = re.findall(r"<script>alert\('(.+)'\);</script>", r.content)
    msg = ""
    if msg_lst:
        msg = msg_lst[0]
    if not msg:
        print  '"%s": ("123456", "%s"),' % (nickname,name)
#     return "nickName: %s name:%s idcard: %s phone: %s %s" % (nickname, name, idcard, phone, msg)


def ident_generator():
    sheng = ('11', '12', '13', '14', '15', '21', '22', '23', '31', '32', '33', '34', '35', '36', '37', '41', '42', '43', '44', '45', '46', '50', '51', '52', '53', '54', '61', '62', '63', '64', '65', '66')
    birthdate = (datetime.date.today() - datetime.timedelta(days = random.randint(7000, 25000)))
    ident = sheng[random.randint(0, 31)] + '0101' + birthdate.strftime("%Y%m%d") + str(random.randint(100, 199))
    coe = {1: 7, 2: 9, 3: 10, 4: 5, 5: 8, 6: 4, 7: 2, 8: 1, 9: 6, 10: 3, 11:7, 12: 9, 13: 10, 14: 5, 15: 8, 16: 4, 17: 2}
    summation = 0
    for i in range(17):
        summation = summation + int(ident[i:i + 1]) * coe[i+1]#ident[i:i+1]使用的是python的切片获得每位数字
    key = {0: '1', 1: '0', 2: 'X', 3: '9', 4: '8', 5: '7', 6: '6', 7: '5', 8: '4', 9: '3', 10: '2'}
    return ident + key[summation % 11]


def start():
    name_list = []
    url_list = [
        "http://zhao.resgain.net/name_list.html",
        "http://shen.resgain.net/name_list.html",
        "http://wang.resgain.net/name_list.html",
        "http://li.resgain.net/name_list.html",
        "http://tzao.resgain.net/name_list.html",
        "http://su.resgain.net/name_list.html",
        "http://huang.resgain.net/name_list.html",
        "http://zhang.resgain.net/name_list.html",
    ]
    for url in url_list:
        r = requests.get(url, headers={"User-Agent": "Chrome3.8"})
        name_list.extend(re.findall(r"/name/(\S+).html", r.content))

    for i in range(50):
        tele = createPhone()
        idcard = ident_generator()
        name = random.choice(list(set(name_list)))
        s = registe(tele, name, idcard, tele)
#         kefu_log.info("[registe_cqky] %s", s)
start()