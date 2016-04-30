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
    line.check_compatible_lines()

    weights = dict.fromkeys(line.compatible_lines.keys(), 1000/len(line.compatible_lines))
    open_city = line.get_open_city()
    if open_city:
        weight_config = open_city.source_weight
        for src, w in weight_config.items():
            if src in weights:
                weights[src] = w

    # 同程不卖当天票， 转交给江苏客运
    if line.crawl_source== "tongcheng" and line.drv_date == dte.now().strftime("%Y-%m-%d"):
        jsky_lineid = line.compatible_lines.get("jsky", "")
        if jsky_lineid:
            return get_flow("jsky"), Line.objects.get(line_id=jsky_lineid)

    choose = weight_choice(weights)
    from app.models import Line
    if not choose:
        return None, None
    new_line = Line.objects.get(line_id=line.compatible_lines[choose])
    return get_flow(choose), new_line
