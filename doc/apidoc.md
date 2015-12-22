---
title: 接口文档
author: 罗军平
description: 推荐用markdown工具打开阅读
---

## [目录](#e79baee5bd95)
* [接口描述](#e68ea5e58fa3e68f8fe8bfb0)
    * [1. 查询出发地](#120e69fa5e8afa2e587bae58f91e59cb0)
    * [2. 查询目的地](#220e69fa5e8afa2e79baee79a84e59cb0)
    * [3. 查询路线](#320e69fa5e8afa2e8b7afe7babf)
    * [4. 提交订单](#420e68f90e4baa4e8aea2e58d95)
    * [5. 订单详情接口](#520e8aea2e58d95e8afa6e68385e68ea5e58fa3)
    * [6. 线路详情接口](#620e7babfe8b7afe8afa6e68385e68ea5e58fa3)
    * [7. 锁票结果回调](#720e99481e7a5a8e7bb93e69e9ce59b9ee8b083)
    * [8. 出票结果回调](#820e587bae7a5a8e7bb93e69e9ce59b9ee8b083)
* [返回状态码](#e8bf94e59b9ee78ab6e68081e7a081)
* [订单状态](#e8aea2e58d95e78ab6e68081)


## 接口描述
#### 1. 查询出发地

##### URL
> [http://192.168.1.202:8000/startings/query]()

###### 支持格式
> JSON

##### 是否需要登陆
> 否

##### HTTP请求方式
> POST

##### 注意事项
> 无

##### 请求体
> 无

##### 返回结果

```javascript

{
    "code": 1,
    "message": "OK",
    "data": [
        {
            "province": "四川",
            "city_list": [
                {
                    "advance_order_time": 120,
                    "city_code": "pzhs",
                    "city_name": "攀枝花市",
                    "end_time": "23:00:00",
                    "is_pre_sell": true,
                    "max_ticket_per_order": 5,
                    "open_time": "07:00:00",
                    "pre_sell_days": 10
                },
                {
                    "advance_order_time": 120,
                    "city_code": "lss",
                    "city_name": "乐山市",
                    "end_time": "23:00:00",
                    "is_pre_sell": true,
                    "max_ticket_per_order": 5,
                    "open_time": "07:00:00",
                    "pre_sell_days": 10
                }
            ]    
        }
    ]
}
```

##### 返回字段说明
>|返回字段|字段类型|说明                             |
>|:-----   |:------|:-----------------------------   |
>|province            | string | 省份 |
>|advance_order_time  | int | 至少提前多久订票，单位(分钟)|
>|city_code           |string | 城市名字拼音缩写    |
>|city_name           |string | 城市名    |
>|end_time            |string | 订票结束时间    |
>|open_time           |string | 订票开放时间    |
>|is_pre_sell         |bool   | 该城市是否支持订票   |
>|max_ticket_per_order| int   | 一个订单最多可购买车票的数量|
>|pre_sell_days       | int   | 预售期                  |

#### 2. 查询目的地

##### URL
> [http://192.168.1.202:8000/destinations/query]()

###### 支持格式
> JSON

##### 是否需要登陆
> 否

##### HTTP请求方式
> POST

##### 注意事项
> 无

##### 请求体

```javascript
{"starting_name":"成都市"}
```

##### 请求字段说明
>|参数|必选|类型|说明|
>|:-----  |:-------  |:-----  |-----|
>|starting_name | 是 | string | 出发地名称 |

##### 返回结果

```javascript

{
    "code": 1,
    "message": "OK",
    "data": [
        "北碚|bb",
        "峨边|eb",
        "峨边|eb",
        "峨边|eb",
        "华蓥|hy",
    ]
}
```

##### 返回字段说明
>|返回字段|字段类型|说明                             |
>|:-----  |:------|:-----------------------------   |
>|data    | array | 目的地数组 |


#### 3. 查询路线

##### URL
> [http://192.168.1.202:8000/lines/query]()

###### 支持格式
> JSON

##### 是否需要登陆
> 否

##### HTTP请求方式
> POST

##### 注意事项
> 无

##### 请求体

```javascript
{
    "starting_name":"成都",
    "destination_name": "成都(八一)",
    "start_date": "2015-12-03"
}
```

##### 请求字段说明
>|参数|必选|类型|说明|
>|:-----  |:-------  |:-----  |-----|
>|starting_name | 是 | string | 出发地名称 |
>|destination_name | 是 | string | 目的地名称 |
>|start_date | 是 | string | 出发日期，格式必须是yyyy-mm-dd|

##### 返回结果

```javascript

{
    "code": 1,
    "data": [
        {
            "bus_num": "LSL1",
            "left_tickets": 0,
            "destination_city": "",
            "destination_station": "成都(八一)",
            "distance": "32",
            "drv_date": "2015-12-03",
            "drv_time": "18:40",
            "fee": 3,
            "full_price": 8,
            "half_price": 4,
            "line_id": "14df7520db3642769f592c528973887b",
            "starting_city": "成都市",
            "starting_station": "昭觉寺车站",
            "vehicle_type": "中型中级"
        }
    ],
    "message": "OK"
}
```

##### 返回字段说明
>|返回字段|字段类型|说明                             |
>|:-----  |:------|:-----------------------------   |
>|bus_num | string | 班次  |
>|left_tickets| int| 余票  |
>|destination_city | string | 目的地城市  |
>|destination_station | string | 目的地站  |
>|distance | string | 距离  |
>|drv_date | string | 发车日期  |
>|drv_time | string | 发车时间  |
>|fee      | float | 手续费  |
>|full_price | float | 全价 |
>|half_price | float | 半价  |
>|line_id | string | 线路id，唯一的  |
>|starting_city | string | 出发城市  |
>|starting_station| string | 出发站  |
>|vehicle_type| string | 车型  |


#### 4. 提交订单

##### URL
> [http://192.168.1.202:8000/orders/submit]()

###### 支持格式
> JSON

##### 是否需要登陆
> 否

##### HTTP请求方式
> POST

##### 注意事项
> 无

##### 请求体

```javascript
 {
    "line_id: "2891249051391980105"             
    "out_order_no": "222"                       
    "order_price: 11                            
    "contact_info:{                             
        "name": "罗军平",                          
        "telephone": "15575101324",             
        "id_type": 1,                           
        "id_number": 431021199004165616,        
        "age_level": 1,                         
    },
    rider_info: [{                              
        "name": "罗军平",                          
        "telephone": "15575101324",             
        "id_type": 1,                           
        "id_number": 431021199004165616,        
        "age_level": 1,                         
    }],
    "locked_return_url: ""                    
    "issued_return_url: ""                    
}
```

##### 请求字段说明
>|参数|必选|类型|说明|
>|:-----  |:-------  |:-----  |-----|
>|line_id | 是 | string | 线路ID|
>|out_order_no| 否 | string | 商户订单号|
>|order_price| 是 | float | 订单金额 |
>|id_type| 是 | int| 证件类型, 1-身份证|
>|id_number| 是 | string| 证件号|
>|age_level | 是 | int | 1-成人 0-儿童|
>|locked_return_url| 否 | string | 锁票回调地址|
>|issued_return_url| 否 | string | 出票回调地址|



##### 返回结果

```javascript
{
   "code": 1,
   "message": "submit order success!"
   "data":{
       "sys_order_no": xxxxxx,
    }
}
```

##### 返回字段说明
>|返回字段|字段类型|说明                             |
>|:-----  |:------|:-----------------------------   |
>|sys_order_no| string | 系统订单号  |


#### 5. 订单详情接口

##### URL
> [http://192.168.1.202:8000/orders/detail]()

###### 支持格式
> JSON

##### 是否需要登陆
> 否

##### HTTP请求方式
> POST

##### 注意事项
> 无

##### 请求体

```javascript
{
    "sys_order_no": "1111"          # 系统订单号
}
```

##### 请求字段说明
>|参数|必选|类型|说明|
>|:-----  |:-------  |:-----  |-----|
>|sys_order_no| string | 系统订单号  |


##### 返回结果

```javascript

{
    "code": 1,
    "message": "OK",
    "data":{
        "out_order_no": "111",      # 商户订单号
        "raw_order_no": "222",      # 源站订单号
        "sys_order_no": "333",      # 系统订单号
        "status": 14,               # 订单状态
        "rider_info":[{             # 乘客信息
            "name":"",
            "telephone": xx,
            "id_type":1,
            "id_number": yy,
            "agen_level": 1,
        }],
        "contacter_info": {
            "name":"",
            "telephone": xx,
            "id_type":1,
            "id_number": yy,
            "agen_level": 1,
        }
        "ticket_info": {                # 车票信息
            "start_city": "",
            "start_station": "",
            "dest_city": "",
            "dest_station": "",
            "drv_date": "",
            "drv_time": "",
            "total_price": "",
        }
     }
```

#### 6. 线路详情接口

##### URL
> [http://192.168.1.202:8000/lines/detail]()

###### 支持格式
> JSON

##### 是否需要登陆
> 否

##### HTTP请求方式
> POST

##### 说明
>  此接口会调源网站的数据以保证数据是最新的，因此返回可能会比较慢。

##### 请求体

```javascript
{
	"line_id": "15328269a5a2b7c3803cf8cf983b932f"
}
```

##### 请求字段说明
>|参数|必选|类型|说明|
>|:-----  |:-------  |:-----  |-----|
>|sys_order_no| string | 系统订单号  |


##### 返回结果

```javascript
{
    "code": 1,
    "data": {
        "bus_num": "5616",
        "destination_city": "",
        "destination_station": "蓬安",
        "distance": "65",
        "drv_date": "2015-12-15",
        "drv_time": "15:30",
        "fee": 3,
        "full_price": 21,
        "half_price": 10.5,
        "left_tickets": 29,
        "line_id": "15328269a5a2b7c3803cf8cf983b932f",
        "starting_city": "南充市",
        "starting_station": "南充客运站",
        "vehicle_type": "中型中级"
    },
    "message": "OK"
}
```

#### 7. 锁票结果回调

##### URL
> 无

###### 支持格式
> JSON

##### 是否需要登陆
> 否

##### HTTP请求方式
> POST

##### 说明
>  返回到下单接口中定义的locked_return_url去

##### 请求体
> 无

##### 返回结果

```javascript
// 成功
{
    "code": 1,
    "data": {
        "out_order_no": "111",      # 商户订单号
        "raw_order_no": "222",      # 源站订单号
        "sys_order_no": "333",      # 系统订单号
        "expire_time": "",
        "total_price": 111.0,
    },
    "message": "OK"
}

//失败
{
    "code": 102,
    "data":{
        "out_order_no": "111",      # 商户订单号
        "raw_order_no": "222",      # 源站订单号
        "sys_order_no": "333",      # 系统订单号
    },
    "message": "lock fail"
}
```

##### 返回字段说明
>|返回字段|字段类型|说明                             |
>|:-----  |:------|:-----------------------------   |
>|expire_time | string | 过期时间戳  |
>|total_price | float | 订单金额|


#### 8. 出票结果回调

##### URL
> 无

###### 支持格式
> JSON

##### 是否需要登陆
> 否

##### HTTP请求方式
> POST

##### 说明
>  返回到下单接口中定义的issued_return_url去

##### 请求体
> 无

##### 返回结果

```javascript
// 成功
{
    "code": 1,
     "data":{
        "out_order_no": "111",      # 商户订单号
        "raw_order_no": "222",      # 源站订单号
        "sys_order_no": "333",      # 系统订单号
        "pick_info":[
            {
                "pick_code": "111",
                "pick_msg": "",
            },
        ],
    },
    "message": "OK"
}

//失败
{
    "code": 103,
    "data":{
        "out_order_no": "111",      # 商户订单号
        "raw_order_no": "222",      # 源站订单号
        "sys_order_no": "333",      # 系统订单号
    },
    "message": "issued fail"
}
```

##### 返回字段说明
>|返回字段|字段类型|说明                             |
>|:-----  |:------|:-----------------------------   |
>|pick_info | array | 取票信息|
>|pick_code | string | 取票验证码, 可能为空|
>|pick_msg | string | 取票文本信息， 可能为空|


#### 返回状态码
>|状态码  |说明      |
>|:-----  |:---------|
>| 1 | 执行成功, 所有>1全部表示出错 |
>| 2 | 参数错误  |
>| 3 | 服务器异常 |
>| 4 | url错误，对应404|
>| 101 | 订单不存在|
>| 102 | 锁票失败|
>| 103 | 出票失败|
>| 201 | 线路不存在|


#### 订单状态
>|状态码  |说明      |
>|:-----  |:---------|
>| 0 | 订单异常关闭或者订单过期|
>| 3 | 锁票成功|
>| 4 | 提交订单(订单初始状态)|
>| 5 | 锁票失败|
>| 6 | 已退票 |
>| 13 | 出票失败|
>| 14 | 出票成功|