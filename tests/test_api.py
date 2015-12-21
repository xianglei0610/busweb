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
        right_day = now + datetime.timedelta(days=random.randint(1, 5))
        wrong_day = now - datetime.timedelta(days=-1)

        data = {
            "starting_name": "成都",
            "destination_name": "成都",
            "start_date": right_day.strftime("%Y-%m-%d")
        }
        r = self.client.post('lines/query', data=json.dumps(data))
        result = json.loads(r.data)
        self.assertEqual(result["code"], RET_OK)
        self.assertNotEqual(result["data"], [])

        data.update(start_date=wrong_day)
        r = self.client.post('lines/query', data=json.dumps(data))
        result = json.loads(r.data)
        self.assertEqual(result["code"], RET_PARAM_ERROR)

    def test_query_line_detail(self):
        data = {"line_id": "wrong line id"}
        response = self.client.post('/lines/query/detail', data=json.dumps(data))
        result = json.loads(response.data)
        self.assertEqual(result['code'], RET_LINE_404)

        old = Line.objects.first()
        data = {"line_id": old.line_id}
        response = self.client.post('/lines/query/detail', data=json.dumps(data))
        result = json.loads(response.data)
        self.assertEqual(result['code'], RET_OK)
        new = Line.objects.get(line_id=old.line_id)
        self.assertNotEqual(old.update_datetime, new.update_datetime)

    def test_order_submit(self):
        now = datetime.datetime.now()
        drv_date = datetime.datetime.strftime(now, "%Y-%m-%d")
        drv_time = datetime.datetime.strftime(now, '%H:%M:%S')
        busLine = Line.objects.filter(crawl_source='bus100', drv_date__gte=drv_date, drv_time__gte=drv_time).order_by('-crawl_datetime').limit(1)
        scLine = Line.objects.filter(crawl_source='scqcp', drv_date__gte=drv_date, drv_time__gte=drv_time).order_by('-crawl_datetime').limit(1)
        lines = []
        if busLine:
            lines.append(busLine[0])
        self.assertTrue(lines != [])
        if scLine:
            lines.append(scLine[0])
        self.assertTrue(len(lines) != 1)
        for line in lines:
            response = self.client.post('/orders/submit',
                data=json.dumps({
                        "line_id": line.line_id,                            # 线路ID
                        "out_order_no": "222",                              # 商户订单号
                        "order_price": line.full_price,                     # 订单金额(总票价)
                        "contact_info": {                                   # 联系人信息
                            "name": "罗军平1",                              # 名字
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
                                       {                                    # 乘客信息
                            "name": "1212",                                 # 名字
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
            self.assertTrue(response.status_code == 200)
            self.assertTrue(result['data'] != [])

    def test_query_order_detail(self):

        response = self.client.post('/orders/detail',
            data=json.dumps({
                    "sys_order_no": "2015121076621582",          # 系统订单号
                    })
            )
        result = json.loads(response.data)
        self.assertTrue(response.status_code == 200)
        self.assertTrue(result['data'] != [])

    def test_refresh_order_status(self):
        response = self.client.post('/orders/refresh',
            data=json.dumps({
                    "sys_order_no": "2015121016375214",          # 系统订单号
                    })
                )
        result = json.loads(response.data)
        self.assertTrue(response.status_code == 200)
        self.assertTrue(result['data'] != [])


class Bus100APITestCase(TestCase):
    def create_app(self):
        app = setup_app(os.getenv('FLASK_CONFIG') or 'local',
                        os.getenv('FLASK_SERVER') or 'api')
        app.config['TESTING'] = True
        return app

    def test_query_destinations(self):
        busStart = Starting.objects.filter(crawl_source='bus100').first()
        scStart = Starting.objects.filter(crawl_source='scqcp').first()
        datas = []
        if busStart:
            datas.append({"starting_name": busStart.city_name})
        if scStart:
            datas.append({"starting_name": scStart.city_name})
        self.assertTrue(datas != [])
        for data in datas:
            response = self.client.post('/destinations/query', data=json.dumps(data))
            result = json.loads(response.data)
            self.assertTrue(response.status_code == 200)
            self.assertTrue(result['data'] != [])

    def test_query_lines(self):
        now = dte.now()
        right_day = now + datetime.timedelta(days=random.randint(1, 5))
        wrong_day = now - datetime.timedelta(days=-1)

        for i in times:
            response = self.client.post('lines/query',
                data=json.dumps({
                "starting_name":"埌东",
                "destination_name": "宝安",
                "start_date": i
                        })
                )
            result = json.loads(response.data)
            self.assertTrue(response.status_code == 200)
            self.assertTrue(result['data'] != [])

    def test_query_line_detail(self):

        response = self.client.post('/lines/query/detail',
            data=json.dumps({
             "line_id": "641811fffd76c0934f0a2eef261f5bf2"  ,
                    })
            )
        result = json.loads(response.data)
        self.assertTrue(response.status_code == 200)
        self.assertTrue(result['data'] != [])

    def test_order_submit(self):
        now = datetime.datetime.now()
        drv_date = datetime.datetime.strftime(now, "%Y-%m-%d")
        drv_time = datetime.datetime.strftime(now, '%H:%M:%S')
        busLine = Line.objects.filter(crawl_source='bus100', drv_date__gte=drv_date, drv_time__gte=drv_time).order_by('-crawl_datetime').limit(1)
        scLine = Line.objects.filter(crawl_source='scqcp', drv_date__gte=drv_date, drv_time__gte=drv_time).order_by('-crawl_datetime').limit(1)
        lines = []
        if busLine:
            lines.append(busLine[0])
        self.assertTrue(lines != [])
        if scLine:
            lines.append(scLine[0])
        self.assertTrue(len(lines) != 1)
        for line in lines:
            response = self.client.post('/orders/submit',
                data=json.dumps({
                        "line_id": line.line_id,                    # 线路ID
                        "out_order_no": "222",                             # 商户订单号
                        "order_price": line.full_price,                                    # 订单金额(总票价)
                        "contact_info": {                                     # 联系人信息
                            "name": "罗军平1",                               # 名字
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
            self.assertTrue(response.status_code == 200)
            self.assertTrue(result['data'] != [])

    def test_query_order_detail(self):

        response = self.client.post('/orders/detail',
            data=json.dumps({
                    "sys_order_no": "2015121076621582",          # 系统订单号
                    })
            )
        result = json.loads(response.data)
        self.assertTrue(response.status_code == 200)
        self.assertTrue(result['data'] != [])

    def test_refresh_order_status(self):
        response = self.client.post('/orders/refresh',
            data=json.dumps({
                    "sys_order_no": "2015121016375214",          # 系统订单号
                    })
                )
        result = json.loads(response.data)
        self.assertTrue(response.status_code == 200)
        self.assertTrue(result['data'] != [])
