# -*- coding:utf-8 -*-

from flask import request, json
from app.main import main
from app.models import Line


@main.route('/startings', methods=['POST'])
def query_starting():
    """
    出发地查询

    Post Body:
    {
        "region_type": "all or city",
    }
    """
    data = json.loads(request.data)
    region_type = data["region_type"]
    if region_type == "city":
        pass
    else:
        pass
