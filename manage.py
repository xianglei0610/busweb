#!/usr/bin/env python
# -*- coding:utf-8 *-*
import os
import pymongo

from app import create_app, db
from flask.ext.script import Manager, Shell

app = create_app(os.getenv('FLASK_CONFIG') or 'default')
manager = Manager(app)


def make_shell_context():
    return dict(app=app, db=db)

manager.add_command("shell", Shell(make_context=make_shell_context))


@manager.command
def deploy():
    from app.models import ScqcpRebot
    ScqcpRebot.check_upsert_all()


@manager.command
def migrate_from_crawl(site):
    from app.models import Line
    crawl_mongo = pymongo.MongoClient("mongodb://%s:%s" % (app.config["host"], app.config["port"]))
    crawl_db = crawl_mongo[app.config["db"]]
    if site == "scqcp":
        for d in crawl_db["scqcp"].find({}):
            line_id = d["line_id"]
            crawl_source = "scqcp"
            attrs = {
                "line_id": line_id,
                "crawl_source": crawl_source,
                "start_city_id": d["city_id"],
                "start_city_name": d["city"],
                "start_sta_id": d["carry_sta_id"],
                "start_sta_name": d["carry_sta_name"],
                "end_city_id": "",
                "end_city_name": "",
                "end_sta_id": "",
                "end_sta_name": d["stop_name"],
                "drv_date_time": d["drv_date_time"],
                "distance": d["mile"],
                "vehicle_type": d["bus_type_name"],
                "seat_type": "",
                "bus_num": d["sch_id"],
                "full_price": d["full_price"],
                "half_price": d["half_price"],
                "crawl_datetime": d["create_datetime"],
                "extra_info": {},
            }
            obj = Line.objects(line_id=line_id, crawl_source=crawl_source)
            if obj:
                obj.update(**attrs)
            else:
                Line(**attrs).save()

if __name__ == '__main__':
    manager.run()
