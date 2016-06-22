# -*- coding:utf-8 *-*
import os
import sys
reload(sys)
sys.setdefaultencoding("utf-8")
import redis
import logging
import flask_profiler

from flask import Flask
from flask.ext.mail import Mail
from flask.ext.mongoengine import MongoEngine
from flask.ext.login import LoginManager
from config import config_mapping
from celery import Celery, platforms
from redis_session import RedisSessionInterface
platforms.C_FORCE_ROOT = True    # celery需要这样
from raven.contrib.flask import Sentry
from logging.handlers import SysLogHandler
from logging import Formatter, StreamHandler, FileHandler


config_name = "%s_%s" % (os.getenv('FLASK_SERVER') or 'api', os.getenv('FLASK_CONFIG') or 'local')
config = config_mapping[config_name]

mail = Mail()
db = MongoEngine()
celery = Celery(__name__, broker=config.CELERY_BROKER_URL)
login_manager = LoginManager()
BASE_DIR = os.path.split(os.path.abspath(os.path.dirname(__file__)))[0]
sentry = Sentry()

line_log = logging.getLogger("line")
order_log = logging.getLogger("order")
kefu_log = logging.getLogger("kefu")
access_log = logging.getLogger("access")
rebot_log = logging.getLogger("rebot")
cron_log = logging.getLogger("cron")
dashboard_log = logging.getLogger("dashboard")


def init_celery(app):
    TaskBase = celery.Task
    celery.conf.update(app.config)

    class ContextTask(TaskBase):
        abstract = True

        def __call__(self, *args, **kwargs):
            with app.app_context():
                return TaskBase.__call__(self, *args, **kwargs)
    celery.Task = ContextTask


def init_logging(app, server_type):
    fmt = Formatter('[%(asctime)s] %(levelname)s: %(message)s')
    stdout_fhd = StreamHandler()
    stdout_fhd.setLevel(logging.INFO)
    stdout_fhd.setFormatter(fmt)
    for k, v in globals().items():
        if not k.endswith("_log"):
            continue
        logger = v
        logger.setLevel(logging.DEBUG)
        s = logger.name
        if config.DEBUG:
            f = "logs/%s.log" % s
            file_hd = FileHandler(os.path.join(BASE_DIR, f))
        else:
            mapping = {
                "order": SysLogHandler.LOG_LOCAL1,
                "line": SysLogHandler.LOG_LOCAL2,
                "common": SysLogHandler.LOG_LOCAL3,
                "access": SysLogHandler.LOG_LOCAL4,
                "cron": SysLogHandler.LOG_LOCAL5,
                "rebot": SysLogHandler.LOG_LOCAL6,
            }
            file_hd = SysLogHandler(address=('10.51.9.34', 514), facility=mapping.get(s, SysLogHandler.LOG_LOCAL3))
        file_hd.setLevel(logging.INFO)
        file_hd.setFormatter(fmt)
        logger.addHandler(stdout_fhd)
        logger.addHandler(file_hd)


def setup_app():
    servers = {
        "api": setup_api_app,
        "dashboard": setup_dashboard_app,
    }
    server_type = config_name.split("_")[0]
    app = servers[server_type]()

    rset = app.config["REDIS_SETTIGNS"]["session"]
    r = redis.Redis(host=rset["host"], port=rset["port"], db=rset["db"])
    app.session_interface = RedisSessionInterface(redis=r)

    sentry.init_app(app, logging=True, level=logging.ERROR)
    init_logging(app, server_type)
    return app


def setup_api_app():
    app = Flask(__name__)
    app.config.from_object(config)
    config.init_app(app)
    print ">>> run api server, use", config.__name__

    mail.init_app(app)
    db.init_app(app)
    init_celery(app)

    from api import api as main_blueprint
    app.register_blueprint(main_blueprint)
    app.secret_key = 'A0Zr98j/3yX R~XHH!jmN]LWX/,?RT'
    flask_profiler.init_app(app)
    return app


def setup_dashboard_app():
    app = Flask(__name__)
    app.config.from_object(config)
    config.init_app(app)
    print ">>> run dashboard server, use", config.__name__

    mail.init_app(app)
    db.init_app(app)
    login_manager.init_app(app)
    init_celery(app)

    from dashboard import dashboard as admin_blueprint
    app.register_blueprint(admin_blueprint)
    app.secret_key = 'A0Zr98j/3yX R~XHH!jmN]LWX/,?RT'
    flask_profiler.init_app(app)
    return app
