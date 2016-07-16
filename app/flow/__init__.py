# -*- coding:utf-8 -*-
import os
import importlib

from app.utils import weight_choice
from datetime import datetime as dte
from app.constants import *

flow_list = {}


def get_flow(site):
    if site not in flow_list:
        cur_dir = os.path.abspath(os.path.dirname(__file__))
        for par, dirs, files in os.walk(cur_dir):
            for f in files:
                if not f.endswith(".py"):
                    continue
                if f in ["base.py", "__init__.py"]:
                    continue
                mod = importlib.import_module("app.flow.%s" % f[:-3])
                cls = mod.Flow
                if cls.name == site:
                    flow_list[cls.name] = cls()
                    break
    return flow_list[site]


def get_compatible_flow(line):
    from app.models import Line
    line.check_compatible_lines()
    weights = dict.fromkeys(line.compatible_lines.keys(), 0)

    open_city = line.get_open_city()
    if open_city:
        open_station = open_city.get_open_station(sta_name=line.s_sta_name)
        if not open_station.source_weight:
            site_list = Line.objects.filter(s_city_name__startswith=open_station.city.city_name, s_sta_name=open_station.sta_name).distinct("crawl_source")
            open_station.modify(source_weight={k: 1000/(len(site_list)) for k in site_list})
        for k, v in open_station.source_weight.items():
            weights[k] = v

    choose = weight_choice(weights)
    if not choose:
        return None, None
    new_line = Line.objects.get(line_id=line.compatible_lines[choose])
    return get_flow(choose), new_line
