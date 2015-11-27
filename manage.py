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
    settings = app.config["CRAWL_MONGODB_SETTINGS"]
    crawl_mongo = pymongo.MongoClient("mongodb://%s:%s" % (settings["host"], settings["port"]))
    crawl_db = crawl_mongo[settings["db"]]

    app.logger.info("start migrate data from crawldb to webdb:%s", site)
    c_cnt, u_cnt = 0, 0
    if site == "scqcp":
        for d in crawl_db["line"].find({}):
            line_id = str(d["line_id"])
            crawl_source = "scqcp"
            attrs = {
                "line_id": line_id,
                "crawl_source": crawl_source,
                "start_city_id": str(d["city_id"]),
                "start_city_name": d["city"],
                "start_sta_id": d["carry_sta_id"],
                "start_sta_name": d["carry_sta_name"],
                "end_city_id": "",
                "end_city_name": "",
                "end_sta_id": "",
                "end_sta_name": d["stop_name"],
                "drv_date_time": d["drv_date_time"],
                "distance": str(d["mile"]),
                "vehicle_type": d["bus_type_name"],
                "seat_type": "",
                "bus_num": d["sch_id"],
                "full_price": str(d["full_price"]),
                "half_price": d["half_price"],
                "crawl_datetime": d["create_datetime"],
                "extra_info": {},
            }
            obj = Line.objects(line_id=line_id, crawl_source=crawl_source)
            if obj:
                u_cnt += 1
                obj.update(**attrs)
            else:
                c_cnt += 1
                Line(**attrs).save()
    app.logger.info("end migrate %s, update %s, create %s", site, u_cnt, c_cnt)

if __name__ == '__main__':
    manager.run()
