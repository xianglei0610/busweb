# -*- coding:utf-8 -*-

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
