# -*- coding:utf-8 -*-

import unittest
import json
import re
import os
from flask import Flask, url_for
from flask.ext.testing import TestCase

from app import setup_app


class APITestCase(TestCase):
    def create_app(self):
        app = setup_app('local', 'api')
        app.config['TESTING'] = True
        return app

    def test_query_startings(self):
        response = self.client.post('/startings/query')
        self.assertTrue(response.status_code == 200)
        result = json.loads(response.data)
        self.assertTrue(result['data'] != [])

    def test_query_destinations(self):

        response = self.client.post('/destinations/query', data=json.dumps({"starting_name": "北海市"}))
        result = json.loads(response.data)
        self.assertTrue(response.status_code == 200)
        self.assertTrue(result['data'] != [])

    def test_query_lines(self):

        response = self.client.post('lines/query',
            data=json.dumps({
            "starting_name":"埌东",             
            "destination_name": "宝安",        
            "start_date": "2015-12-07"         
                    })
            )
        result = json.loads(response.data)
        self.assertTrue(response.status_code == 200)
        self.assertTrue(result['data'] != [])

    def test_order_submit(self):

        response = self.client.post('/orders/submit',
            data=json.dumps({
                    "line_id": "69e8f91d0074f940af409e4677967f7f",                    # 线路ID
                    "out_order_no": "222",                             # 商户订单号
                    "order_price": 11,                                    # 订单金额(总票价)
                    "contact_info": {                                     # 联系人信息
                        "name": "罗军平",                               # 名字
                        "telephone": "15575101324",                     # 手机
                        "id_type": 1,                                   # 证件类型
                        "id_number": 431021199004165616,                # 证件号
                        "age_level": 1,                                 # 大人 or 小孩
                    },
                    "rider_info": [{                                      # 乘客信息
                        "name": "罗军平",                               # 名字
                        "telephone": "15575101324",                     # 手机
                        "id_type": 1,                                   # 证件类型
                        "id_number": 431021199004165616,                # 证件号
                        "age_level": 1,                                 # 大人 or 小孩
                    },
                                   {                                      # 乘客信息
                        "name": "1212",                               # 名字
                        "telephone": "15575101324",                     # 手机
                        "id_type": 1,                                   # 证件类型
                        "id_number": 431021199004165615,                # 证件号
                        "age_level": 1,                                 # 大人 or 小孩
                    }],
                    "locked_return_url": "",                   # 锁票成功回调地址
                    "issued_return_url": ""                    # 出票成功回调地址
                })
            )
        result = json.loads(response.data)
        print result
        self.assertTrue(response.status_code == 200)
        self.assertTrue(result['data'] != [])

    def test_query_order_detail(self):

        response = self.client.post('/orders/detail',
            data=json.dumps({
                    "sys_order_no": "2015120783653723",          # 系统订单号
                    })
            )
        result = json.loads(response.data)
        print result
        self.assertTrue(response.status_code == 200)
        self.assertTrue(result['data'] != [])

    def test_refresh_order_status(self):
        response = self.client.post('/orders/refresh',
            data=json.dumps({
                    "sys_order_no": "2015120783653723",          # 系统订单号
                    })
                )
        result = json.loads(response.data)
        print result
        self.assertTrue(response.status_code == 200)
        self.assertTrue(result['data'] != [])
if __name__ == '__main__':
    unittest.main()
