#!/usr/bin/env python
# -*- coding:utf-8 *-*
import os
import sys
import pymongo
import multiprocessing

from datetime import datetime
from pypinyin import lazy_pinyin
from app import setup_app, db
from app.utils import md5
from flask.ext.script import Manager, Shell
from app.models import Line, Starting, Destination


def insert_or_update_starting(line):
    starting_attrs = {
        "starting_id": md5("%s-%s-%s-%s" % (line["s_province"], line["s_city_name"], line["s_sta_name"], line["crawl_source"])),
        "province_name": line["s_province"],
        "city_id": "",
        "city_name": line["s_city_name"],
        "station_id": "",
        "station_name": line["s_sta_name"],
        "city_pinyin": "".join(lazy_pinyin(line["s_city_name"])),
        "city_pinyin_prefix": "".join(map(lambda w: w[0], lazy_pinyin(line["s_city_name"]))),
        "station_pinyin": "".join(lazy_pinyin(line["s_sta_name"])),
        "station_pinyin_prefix": "".join(map(lambda w: w[0], lazy_pinyin(line["s_sta_name"]))),
        "is_pre_sell": True,
        "crawl_source": line["crawl_source"],
    }
    try:
        starting_obj = Starting.objects.get(starting_id=starting_attrs["starting_id"])
        starting_obj.update(**starting_attrs)
    except Starting.DoesNotExist:
        starting_obj = Starting(**starting_attrs)
        starting_obj.save()
    return starting_obj


def insert_or_update_destination(starting, line):
    city_name = line["d_city_name"]
    station_name = line["d_sta_name"]
    crawl_source = line["crawl_source"]
    dest_attrs = {
        "destination_id": md5("%s-%s-%s-%s" % (starting.starting_id, city_name, station_name, crawl_source)),
        "starting": starting,
        "city_id": "",
        "city_name": city_name,
        "city_pinyin": "".join(lazy_pinyin(city_name)),
        "city_pinyin_prefix": "".join(map(lambda w: w[0], lazy_pinyin(city_name))),
        "station_id": "",
        "station_name": station_name,
        "station_pinyin": "".join(lazy_pinyin(station_name)),
        "station_pinyin_prefix": "".join(map(lambda w: w[0], lazy_pinyin(station_name))),
        "crawl_source": crawl_source,
    }
    try:
        dest_obj = Destination.objects.get(destination_id=dest_attrs["destination_id"])
        dest_obj.update(**dest_attrs)
    except Destination.DoesNotExist:
        dest_obj = Destination(**dest_attrs)
        dest_obj.save()
    return dest_obj


def insert_or_update_line(starting, destination, line):
    attrs = {
        "line_id": line["line_id"],
        "crawl_source": line["crawl_source"],
        "starting": starting,
        "destination": destination,
        "drv_date": line["drv_date"],
        "drv_time": line["drv_time"],
        "drv_datetime": line["drv_datetime"],
        "distance": str(line["distance"]),
        "vehicle_type": line["vehicle_type"],
        "seat_type": line["seat_type"],
        "bus_num": line["bus_num"],
        "full_price": line["full_price"],
        "half_price": line["half_price"],
        "crawl_datetime": line["crawl_datetime"],
        "fee": line["fee"],
        "left_tickets": line["left_tickets"],
        "extra_info": line["extra_info"],
        'update_datetime': datetime.now(),
    }
    try:
        line_obj = Line.objects.get(line_id=attrs["line_id"])
        line_obj.update(**attrs)
    except Line.DoesNotExist:
        line_obj = Line(**attrs)
        line_obj.save()
    return line_obj


def migrate_scqcp(crawl_db, city=""):
    for d in crawl_db.scqcp_line.find({"drv_date_time": {"$gte": datetime.now().strftime("%Y-%m-%d %H:%M")}}):
        crawl_source = "scqcp"
        # migrate Starting
        city_id = str(d["city_id"])
        starting_id = md5("%s-%s-%s-%s-%s" % \
                (city_id, d["city"], d["carry_sta_id"], d["carry_sta_name"], crawl_source))
        start_city = crawl_db.scqcp_start_city.find_one({"city_id": d["city_id"]})
        starting_attrs = {
            "starting_id": starting_id,
            "province_name": "四川",
            "city_id": city_id,
            "city_name": d["city"],
            "station_id": d["carry_sta_id"],
            "station_name": d["carry_sta_name"],
            "city_pinyin": start_city["en_name"],
            "city_pinyin_prefix": start_city["short_name"],
            "station_pinyin": "",
            "station_pinyin_prefix": "",
            "is_pre_sell": start_city["is_pre_sell"],
            "crawl_source": crawl_source,
        }
        try:
            starting_obj = Starting.objects.get(starting_id=starting_id)
            starting_obj.update(**starting_attrs)
        except Starting.DoesNotExist:
            starting_obj = Starting(**starting_attrs)
            starting_obj.save()

        # migrate destination
        dest_id = md5("%s-%s-%s-%s-%s-%s" % \
                (starting_obj.starting_id, "", "", d["stop_code"], d["stop_name"], crawl_source))
        target_city = crawl_db.scqcp_target_city.find_one({"starting_city_id": d["city_id"], "stop_name":
            d["stop_alias_name"]})
        dest_attrs = {
            "destination_id": dest_id,
            "starting": starting_obj,
            "city_id": "",
            "city_name": "",
            "city_pinyin": "",
            "city_pinyin_prefix": "",
            "station_id": "",
            "station_name": target_city["stop_name"],
            "station_pinyin": target_city["en_name"],
            "station_pinyin_prefix": target_city["short_name"],
            "crawl_source": "scqcp",
        }
        try:
            dest_obj = Destination.objects.get(destination_id=dest_id)
            dest_obj.update(**dest_attrs)
        except Destination.DoesNotExist:
            dest_obj = Destination(**dest_attrs)
            dest_obj.save()

        # migrate Line
        line_id = str(d["line_id"])
        drv_date, drv_time = d["drv_date_time"].split(" ")
        attrs = {
            "line_id": line_id,
            "crawl_source": crawl_source,
            "starting": starting_obj,
            "destination": dest_obj,
            "drv_date": drv_date,
            "drv_time": drv_time,
            "drv_datetime": datetime.strptime(d["drv_date_time"], "%Y-%m-%d %H:%M"),
            "distance": str(d["mile"]),
            "vehicle_type": d["bus_type_name"],
            "seat_type": "",
            "bus_num": d["sch_id"],
            "full_price": str(d["full_price"]),
            "half_price": d["half_price"],
            "crawl_datetime": d["create_datetime"],
            "fee": d["service_price"],
            "left_tickets": d["amount"],
            "extra_info": {"sign_id": d["sign_id"], "stop_name_short": d["stop_name"]},
            'update_datetime': datetime.now(),
        }
        try:
            line_obj = Line.objects.get(line_id=line_id, crawl_source=crawl_source)
            line_obj.update(**attrs)
        except Line.DoesNotExist:
            line_obj = Line(**attrs)
            line_obj.save()
        print line_obj.line_id


def migrate_bus100(crawl_db, city=""):
    for d in crawl_db.line_bus100.find({"departure_time": {"$gte": str(datetime.now())}}):
        crawl_source = "bus100"

        # migrate Starting
        city_id = str(d["city_id"])
        starting_id = md5("%s-%s-%s-%s-%s" % \
                (city_id, d["city_name"], d["start_city_id"], d["start_city_name"], crawl_source))
        start_city = crawl_db.start_city_bus100.find_one({"start_city_id": d["start_city_id"]})

        starting_attrs = {
            "starting_id": starting_id,
            "province_name": d["province_name"],
            "city_id": city_id,
            "city_name": d["city_name"],
            "station_id": d["start_city_id"],
            "station_name": d["start_city_name"],
            "city_pinyin": '',
            "city_pinyin_prefix": start_city["city_short_name"],
            "station_pinyin": start_city["start_full_name"],
            "station_pinyin_prefix": start_city["start_short_name"],
            "is_pre_sell": True,
            "crawl_source": crawl_source,
        }
        try:
            starting_obj = Starting.objects.get(starting_id=starting_id)
            starting_obj.update(**starting_attrs)
        except Starting.DoesNotExist:
            starting_obj = Starting(**starting_attrs)
            starting_obj.save()

        # migrate destination
        dest_id  = md5("%s-%s-%s-%s-%s-%s" % \
                (starting_obj.starting_id, "", "", "", d["target_city_name"], crawl_source))
        target_city = crawl_db.target_city_bus100.find_one({"starting_id": d["start_city_id"], "target_name": d["target_city_name"]})
        dest_attrs = {
            "destination_id": dest_id,
            "starting": starting_obj,
            "city_id": "",
            "city_name": "",
            "city_pinyin": "",
            "city_pinyin_prefix": "",
            "station_id": "",
            "station_name": target_city["target_name"],
            "station_pinyin": target_city["full_name"],
            "station_pinyin_prefix": target_city["short_name"],
            "crawl_source": crawl_source,
        }
        try:
            dest_obj = Destination.objects.get(destination_id=dest_id)
            dest_obj.update(**dest_attrs)
        except Destination.DoesNotExist:
            dest_obj = Destination(**dest_attrs)
            dest_obj.save()

        # migrate Line
        line_id = str(d["line_id"])
        drv_date, drv_time = d["departure_time"].split(" ")
        attrs = {
            "line_id": line_id,
            "crawl_source": crawl_source,
            "starting": starting_obj,
            "destination": dest_obj,
            "drv_date": drv_date,
            "drv_time": drv_time,
            "drv_datetime": datetime.strptime(d["departure_time"], "%Y-%m-%d %H:%M"),
            "distance": str(d["distance"]),
            "vehicle_type": '',
            "seat_type": "",
            "bus_num": str(d["shiftid"]),
            "full_price": float(str(d["price"]).split('￥')[-1]),
            "half_price": 0,
            "crawl_datetime": d["crawl_time"],
            "fee": 0,
            "left_tickets": 50 if d["flag"] else 0,
            "extra_info": {"flag": d["flag"]},
            'update_datetime': datetime.now(),
        }
        try:
            line_obj = Line.objects.get(line_id=line_id, crawl_source=crawl_source)
            line_obj.update(**attrs)
        except Line.DoesNotExist:
            line_obj = Line(**attrs)
            line_obj.save()
        print line_obj.line_id


def migrate_ctrip(crawl_db, city=""):
    query = {
        "drv_datetime": {
            "$gte": datetime.now()
        },
    }
    if city:
        query.update({"s_city_name": city})
    for d in crawl_db.ctrip_line.find(query):
        starting = insert_or_update_starting(d)
        destination = insert_or_update_destination(starting, d)
        line_obj = insert_or_update_line(starting, destination, d)
        print line_obj.line_id, d["s_city_name"]
