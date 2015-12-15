
# -*- coding:utf-8 *-*
import os
import sys
reload(sys)
sys.setdefaultencoding("utf-8")
from app import setup_app, celery

app = setup_app(os.getenv('FLASK_CONFIG') or 'local',
                os.getenv('FLASK_SERVER') or 'api')
