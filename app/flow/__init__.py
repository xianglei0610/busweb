# -*- coding:utf-8 -*-
from app.utils import weight_choice
from app.constants import *

flow_list = {}


def get_flow(site=""):
    if site not in flow_list:
        import bus100
        import scqcp
        import ctrip
        import cbd
        import jsky
        import baba
        for mod in [bus100, scqcp, ctrip, cbd, jsky, baba]:
            cls = mod.Flow
            if cls.name == site:
                flow_list[cls.name] = cls()
                break
    return flow_list[site]


def get_compatible_flow(line):
    line.check_compatible_lines()
    weights = {}
    for src, line_id in line.compatible_lines.items():
        weights[src] = WEIGHTS[src]
    choose = weight_choice(weights)
    from app.models import Line
    new_line = Line.objects.get(line_id=line.compatible_lines[choose])
    return get_flow(choose), new_line
