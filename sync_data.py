#!/usr/bin/env python
# -*- coding:utf-8 *-*
import pypinyin
from datetime import datetime
from app.models import Line


def migrate_bus100(crawl_db, city=""):
#     Line.objects.filter(crawl_source='bus100').delete()
#     Destination.objects.filter(crawl_source='bus100').delete()
#     Starting.objects.filter(crawl_source='bus100').delete()

    query = {
        "departure_time": {
           "$gte": str(datetime.now())
        },
    }
    if city:
        query.update({"start_city_name": city})
    for d in crawl_db.line_bus100.find(query):
        crawl_source = d["crawl_source"]
        target_city_name = d["target_city_name"]
        end_station = d["end_station"]
        d_city_code = d["target_short_name"]
        if not d_city_code:
            d_city_code = "".join(map(lambda x:x[0], pypinyin.pinyin(unicode(target_city_name), style=pypinyin.FIRST_LETTER)))

        drv_date, drv_time = d["departure_time"].split(" ")
        attrs = {
            "line_id": d["line_id"],
            "crawl_source": crawl_source,
            "s_province": d["province_name"],
            "s_city_id": d["start_city_id"],
            "s_city_name": d["start_city_name"],
            "s_sta_id": d["start_city_id"],
            "s_sta_name": d["start_station"],
            "s_city_code": d["start_short_name"],
            "d_city_name": target_city_name,
            "d_city_code": d_city_code,
            "d_sta_name": end_station,
            "drv_date": drv_date,
            "drv_time": drv_time,
            "drv_datetime": datetime.strptime(d["departure_time"], "%Y-%m-%d %H:%M"),
            "distance": str(d["distance"]),
            "vehicle_type": '',
            "seat_type": '',
            "bus_num": str(d["banci"]),
            "full_price": float(str(d["price"]).split('￥')[-1]),
            "half_price": 0,
            "crawl_datetime": d["crawl_time"],
            "fee": 0,
            "left_tickets": 50 if d["flag"] else 0,
            "extra_info": {"flag": d["flag"]},
            'update_datetime': datetime.now(),
            "shift_id": str(d["shiftid"]),
        }
        try:
            line_obj = Line.objects.get(line_id=attrs["line_id"])
            line_obj.update(**attrs)
        except Line.DoesNotExist:
            line_obj = Line(**attrs)
            line_obj.save()
        print line_obj.line_id, d["start_city_name"]
