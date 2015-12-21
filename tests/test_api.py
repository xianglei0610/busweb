# -*- coding:utf-8 -*-
import json
import os
import datetime
import random

from app.constants import *
from datetime import datetime as dte
from flask.ext.testing import TestCase
from app.models import Line, Starting
from app import setup_app


class CommonAPITestCase(TestCase):
    """
    测试跟第三方网站数据无关的接口
    """

    def create_app(self):
        app = setup_app(os.getenv('FLASK_CONFIG') or 'local',
                        os.getenv('FLASK_SERVER') or 'api')
        app.config['TESTING'] = True
        return app

    def test_query_startings(self):
        response = self.client.post('/startings/query')
        self.assertTrue(response.status_code == 200)
        result = json.loads(response.data)
        self.assertTrue(result['data'] != [])
        self.assertEqual(result['code'], RET_OK)

    def test_query_order_detail(self):

        order = Order.objects.first()
        response = self.client.post('/orders/detail',
            data=json.dumps({
                    "sys_order_no": order.order_no,          # 系统订单号
                    })
            )
        result = json.loads(response.data)
        self.assertEqual(result['code'], RET_OK)
        self.assertTrue(result['data'] != [])


class ScqcpAPITestCase(TestCase):
    def create_app(self):
        app = setup_app(os.getenv('FLASK_CONFIG') or 'local',
                        os.getenv('FLASK_SERVER') or 'api')
        app.config['TESTING'] = True
        return app

    def test_query_destinations(self):
        data = {"starting_name": "成都"}
        response = self.client.post('/destinations/query', data=json.dumps(data))
        result = json.loads(response.data)
        self.assertEqual(result["code"], RET_OK)
        self.assertNotEqual(result["data"], [])

        data = {"starting_name": ""}
        response = self.client.post('/destinations/query', data=json.dumps(data))
        result = json.loads(response.data)
        self.assertEqual(result["code"], RET_PARAM_ERROR)

    def test_query_lines(self):
        now = dte.now()
        right_day = now + datetime.timedelta(days=1)
        wrong_day = now - datetime.timedelta(days=1)

        data = {
            "starting_name": "成都",
            "destination_name": "成都",
            "start_date": right_day.strftime("%Y-%m-%d")
        }
        r = self.client.post('lines/query', data=json.dumps(data))
        result = json.loads(r.data)
        self.assertEqual(result["code"], RET_OK)
        self.assertNotEqual(result["data"], [])

        data.update(start_date=wrong_day.strftime("%Y-%m-%d"))
        r = self.client.post('lines/query', data=json.dumps(data))
        result = json.loads(r.data)
        self.assertEqual(result["code"], RET_PARAM_ERROR)

    def test_query_line_detail(self):
        data = {"line_id": "wrong line id"}
        response = self.client.post('/lines/detail', data=json.dumps(data))
        result = json.loads(response.data)
        self.assertIn(result['code'], [RET_LINE_404, RET_PAGE_404])

        old = Line.objects.filter(crawl_source="scqcp").first()
        data = {"line_id": old.line_id}
        response = self.client.post('/lines/detail', data=json.dumps(data))
        result = json.loads(response.data)
        self.assertEqual(result['code'], RET_OK)
        new = Line.objects.get(line_id=old.line_id)
        self.assertNotEqual(old.update_datetime, new.update_datetime)

    def test_order_submit(self):
        line = Line.objects.filter(crawl_source='scqcp').order_by('-crawl_datetime').first()
        response = self.client.post('/orders/submit',
            data=json.dumps({
                    "line_id": line.line_id,                            # 线路ID
                    "out_order_no": "222",                              # 商户订单号
                    "order_price": line.real_price(),                     # 订单金额(总票价)
                    "contact_info": {                                   # 联系人信息
                        "name": "罗军平",                              # 名字
                        "telephone": "15575101324",                     # 手机
                        "id_type": 1,                                   # 证件类型
                        "id_number": 431021199004165616,                # 证件号
                        "age_level": 1,                                 # 大人 or 小孩
                    },
                    "rider_info": [{                                    # 乘客信息
                        "name": "罗军平",                               # 名字
                        "telephone": "15575101324",                     # 手机
                        "id_type": 1,                                   # 证件类型
                        "id_number": 431021199004165616,                # 证件号
                        "age_level": 1,                                 # 大人 or 小孩
                    },
                    ],
                    "locked_return_url": "",                   # 锁票成功回调地址
                    "issued_return_url": ""                    # 出票成功回调地址
                })
            )
        result = json.loads(response.data)
        self.assertEqual(result['code'], RET_OK)
        self.assertTrue(result['data'] != [])


class Bus100APITestCase(TestCase):
    def create_app(self):
        app = setup_app(os.getenv('FLASK_CONFIG') or 'local',
                        os.getenv('FLASK_SERVER') or 'api')
        app.config['TESTING'] = True
        return app

    def test_query_destinations(self):
        data = {"starting_name": "柳州市"}
        response = self.client.post('/destinations/query', data=json.dumps(data))
        result = json.loads(response.data)
        self.assertEqual(result["code"], RET_OK)
        self.assertNotEqual(result["data"], [])

        data = {"starting_name": ""}
        response = self.client.post('/destinations/query', data=json.dumps(data))
        result = json.loads(response.data)
        self.assertEqual(result["code"], RET_PARAM_ERROR)

    def test_query_lines(self):
        now = dte.now()
        right_day = now + datetime.timedelta(days=1)
        wrong_day = now - datetime.timedelta(days=1)

        data = {
            "starting_name": "柳州市",
            "destination_name": "桂林",
            "start_date": right_day.strftime("%Y-%m-%d")
        }
        r = self.client.post('lines/query', data=json.dumps(data))
        result = json.loads(r.data)
        self.assertEqual(result["code"], RET_OK)
        self.assertNotEqual(result["data"], [])

        data.update(start_date=wrong_day.strftime("%Y-%m-%d"))
        r = self.client.post('lines/query', data=json.dumps(data))
        result = json.loads(r.data)
        self.assertEqual(result["code"], RET_PARAM_ERROR)

    def test_query_line_detail(self):
        data = {"line_id": "wrong line id"}
        response = self.client.post('/lines/detail', data=json.dumps(data))
        result = json.loads(response.data)
        self.assertIn(result['code'], [RET_LINE_404, RET_PAGE_404])

        old = Line.objects.filter(crawl_source="bus100").first()
        data = {"line_id": old.line_id}
        response = self.client.post('/lines/detail', data=json.dumps(data))
        result = json.loads(response.data)
        self.assertEqual(result['code'], RET_OK)
        new = Line.objects.get(line_id=old.line_id)
        self.assertNotEqual(old.update_datetime, new.update_datetime)

    def test_order_submit(self):
        line = Line.objects.filter(crawl_source='scqcp').order_by('-crawl_datetime').first()
        response = self.client.post('/orders/submit',
            data=json.dumps({
                    "line_id": line.line_id,                            # 线路ID
                    "out_order_no": "222",                              # 商户订单号
                    "order_price": line.real_price(),                     # 订单金额(总票价)
                    "contact_info": {                                   # 联系人信息
                        "name": "罗军平",                              # 名字
                        "telephone": "15575101324",                     # 手机
                        "id_type": 1,                                   # 证件类型
                        "id_number": 431021199004165616,                # 证件号
                        "age_level": 1,                                 # 大人 or 小孩
                    },
                    "rider_info": [{                                    # 乘客信息
                        "name": "罗军平",                               # 名字
                        "telephone": "15575101324",                     # 手机
                        "id_type": 1,                                   # 证件类型
                        "id_number": 431021199004165616,                # 证件号
                        "age_level": 1,                                 # 大人 or 小孩
                    },
                    ],
                    "locked_return_url": "",                   # 锁票成功回调地址
                    "issued_return_url": ""                    # 出票成功回调地址
                })
            )
        result = json.loads(response.data)
        self.assertEqual(result['code'], RET_OK)
        self.assertTrue(result['data'] != [])

