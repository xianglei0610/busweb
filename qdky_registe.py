#!/usr/bin/env python
# encoding: utf-8
import os
import random
import datetime
import requests
import re
import urllib
import json
from datetime import date, timedelta
from bs4 import BeautifulSoup
from app.utils import vcode_cqky
from app import kefu_log

BASE_DIR = os.path.dirname(os.path.dirname(__file__))
DC_PATH = BASE_DIR + "districtcode.txt"

url = 'http://ticket.qdjyjt.com/'
headers = {
    'User-Agent': 'Mozilla/5.0 (Windows NT 6.1; WOW64; rv:48.0) Gecko/20100101 Firefox/48.0',
    "Upgrade-Insecure-Requests": 1,
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
    r = requests.get(url, headers=headers)
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


def create_name():
    username_list = []
    count = 7
    for i in range(30):
        letter_count = random.randint(0, count)
        shuzi_count = 7-letter_count
        letter = ''.join(random.sample(['z','y','x','w','v','u','t','s','r','q','p','o','n','m','l','k','j','i','h','g','f','e','d','c','b','a'], letter_count))
        shuzi = str(random.randint(10**shuzi_count, 10**(shuzi_count+1)-1))
        username = letter + shuzi
        if username not in username_list:
            username_list.append(username)
    return username_list


def qdky_account(headers, cookies, state, valid):
    checkcode = raw_input('请输入验证码:')
    username_list = create_name()
    print username_list
    check_list = []
    url = 'http://ticket.qdjyjt.com/'
    check_url = "http://ticket.qdjyjt.com/register.aspx/IsUserNameExist"
    reg_headers = headers
    headers.update({'Content-Type': 'application/json; charset=utf-8',
                    "Referer":"http://ticket.qdjyjt.com/register.aspx",
                    "X-Requested-With" : "XMLHttpRequest",
                    "Host":"ticket.qdjyjt.com"})
    for usename in username_list:
        data = {"userName": usename}
        headers.update({"X-Requested-With" : "XMLHttpRequest",
                        'Content-Type': 'application/json; charset=utf-8'})
        res = requests.post(check_url, data=json.dumps(data), headers=headers,
                            cookies=cookies)
        res = res.json()
        if res.get('d', '') == 'ok':
            data = {
                '__EVENTTARGET': '',
                '__EVENTARGUMENT': '',
                '__VIEWSTATE': state,
                '__EVENTVALIDATION': valid,
                "Button_3_tj":u"提交注册信息",
                'DropDownList2':u'男',
                "TextBox10" :'',
                "TextBox7":'',       
                "TextBox9":'',
                "aa":'',
                "checktxt":checkcode,
                "repwd":"123456",
                "userpwd":"123456" ,
                "txtUserName": usename,
            }
            reg_headers.update({
                'User-Agent': 'Mozilla/5.0 (Windows NT 6.1; WOW64; rv:48.0) Gecko/20100101 Firefox/48.0',
                "Upgrade-Insecure-Requests": "1",
                "Content-Type":"application/x-www-form-urlencoded",
                "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8"
                })

            del reg_headers['X-Requested-With']

            register_url = "http://ticket.qdjyjt.com/register.aspx"
            res = requests.post(register_url, data=data,
                                cookies=cookies, headers=reg_headers)
            if "验证码错误" not in res.content and "afterregister();" in res.content:
                check_list.append(usename)
                print '"%s": ("123456", ""),' % (usename) 
    print check_list


def main():
    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 6.1; WOW64; rv:48.0) Gecko/20100101 Firefox/48.0',
        "Upgrade-Insecure-Requests": "1",
    }
    cookies ={"ASP.NET_SessionId":"vbxh3zde0shhyhbzssdcq2i5"}
    headers.update({
               "Content-Type":"application/x-www-form-urlencoded",
    })
    register_url = "http://ticket.qdjyjt.com/register.aspx"
    r = requests.get(register_url, headers=headers, cookies=cookies)
    cookies.update(dict(r.cookies))
    soup = BeautifulSoup(r.content, "lxml")
    state = soup.find('input', attrs={'id': '__VIEWSTATE'}).get('value', '')
    valid = soup.find('input', attrs={'id': '__EVENTVALIDATION'}).get('value', '')
    
    data = {
        '__EVENTTARGET': '',
        '__EVENTARGUMENT': '',
        '__VIEWSTATE': state,
        '__EVENTVALIDATION': valid,
        "Button_5_ty":"同 意"
    }
    r = requests.post(register_url, headers=headers, cookies=cookies, data=data)
    cookies.update(dict(r.cookies))
    soup = BeautifulSoup(r.content, "lxml")
    state = soup.find('input', attrs={'id': '__VIEWSTATE'}).get('value', '')
    valid = soup.find('input', attrs={'id': '__EVENTVALIDATION'}).get('value', '')
    code_url = 'http://ticket.qdjyjt.com/yzm.aspx'
    image_headers = headers
    del image_headers['Content-Type']
    r = requests.get(code_url, headers=image_headers, cookies=cookies)

    with open('test.jpg', "wb") as code:
        code.write(r.content) 
    qdky_account(headers, cookies, state, valid)
main()

