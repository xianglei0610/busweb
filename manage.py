#!/usr/bin/env python
# -*- coding:utf-8 *-*
import os
import pymongo

from datetime import datetime
from app import setup_app, db, app
from flask.ext.script import Manager, Shell

setup_app(os.getenv('FLASK_CONFIG') or 'default')
manager = Manager(app)

def make_shell_context():
    return dict(app=app, db=db)

manager.add_command("shell", Shell(make_context=make_shell_context))


@manager.command
def deploy():
    from app.models import ScqcpRebot, Gx84100Rebot
    ScqcpRebot.check_upsert_all()
    Gx84100Rebot.check_upsert_all()


@manager.command
def migrate_from_crawl(site):
    from app.models import Line, Starting, Destination
    settings = app.config["CRAWL_MONGODB_SETTINGS"]
    crawl_mongo = pymongo.MongoClient("mongodb://%s:%s" % (settings["host"], settings["port"]))
    crawl_db = crawl_mongo[settings["db"]]

    def migrate_scqcp():
        for d in crawl_db.scqcp_line.find({}):
            crawl_source = "scqcp"

            # migrate Starting
            city_id = str(d["city_id"])
            starting_id = str(hash("%s-%s-%s-%s-%s" % \
                    (city_id, d["city"], d["carry_sta_id"], d["carry_sta_name"], crawl_source)))
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
            dest_id  = str(hash("%s-%s-%s-%s-%s-%s" % \
                    (starting_obj.starting_id, "", "", d["stop_code"], d["stop_name"], crawl_source)))
            target_city = crawl_db.scqcp_target_city.find_one({"starting_city_id": d["city_id"], "stop_name": d["stop_name"]})
            dest_attrs = {
                "destination_id": dest_id,
                "starting": starting_obj,
                "city_id": "",
                "city_name": "",
                "city_pinyin": "",
                "city_pinyin_prefix": "",
                "station_id": "",
                "station_name": d["stop_name"],
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
                "distance": str(d["mile"]),
                "vehicle_type": d["bus_type_name"],
                "seat_type": "",
                "bus_num": d["sch_id"],
                "full_price": str(d["full_price"]),
                "half_price": d["half_price"],
                "crawl_datetime": d["create_datetime"],
                "fee": d["service_price"],
                "extra_info": {"left_ticket": d["amount"], "sign_id": d["sign_id"]},
            }
            try:
                line_obj = Line.objects.get(line_id=line_id, crawl_source=crawl_source)
                line_obj.update(**attrs)
            except Line.DoesNotExist:
                line_obj = Line(**attrs)
                line_obj.save()

    def migrate_gx84100():
        for d in crawl_db.line_gx84100.find({}):
            crawl_source = "gx84100"

            # migrate Starting
            city_id = str(d["city_id"])
            starting_id = str(hash("%s-%s-%s-%s-%s" % \
                    (city_id, d["city_name"], d["start_city_id"], d["start_city_name"], crawl_source)))
            start_city = crawl_db.start_city_gx84100.find_one({"city_id": d["city_id"]})
            starting_attrs = {
                "starting_id": starting_id,
                "province_name": u"广西",
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
            dest_id  = str(hash("%s-%s-%s-%s-%s-%s" % \
                    (starting_obj.starting_id, "", "", "", d["target_city_name"], crawl_source)))
            print d["start_city_id"],d["target_city_name"]
            target_city = crawl_db.target_city_gx84100.find_one({"starting_id": d["start_city_id"], "target_name": d["target_city_name"]})
            print target_city
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
                "distance": str(d["distance"]),
                "vehicle_type": '',
                "seat_type": "",
                "bus_num": str(d["shiftid"]),
                "full_price": float(str(d["price"]).split('￥')[-1]),
                "half_price": 0,
                "crawl_datetime": d["crawl_time"],
                "fee": 0,
                "extra_info": {"flag": d["flag"]},
            }
            print attrs
            try:
                line_obj = Line.objects.get(line_id=line_id, crawl_source=crawl_source)
                line_obj.update(**attrs)
            except Line.DoesNotExist:
                line_obj = Line(**attrs)
                line_obj.save()
                
    app.logger.info("start migrate data from crawldb to webdb:%s", site)
    if site == "scqcp":
        migrate_scqcp()
    elif site == 'gx84100':
        migrate_gx84100()
    app.logger.info("end migrate %s" % site)


if __name__ == '__main__':
    manager.run()
