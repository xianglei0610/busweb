# -*- coding:utf-8 *-*
import os
import sys
reload(sys)
sys.setdefaultencoding("utf-8")
import redis
import logging

from flask import Flask
from flask.ext.mail import Mail
from flask.ext.mongoengine import MongoEngine
from flask.ext.login import LoginManager
from config import config
from celery import Celery, platforms
from redis_session import RedisSessionInterface
platforms.C_FORCE_ROOT = True    # celery需要这样
from raven.contrib.flask import Sentry
from logging.handlers import TimedRotatingFileHandler
from logging import Formatter, StreamHandler

mail = Mail()
db = MongoEngine()
celery = Celery(__name__, broker="redis://localhost:6379/10")
login_manager = LoginManager()
BASE_DIR = os.path.split(os.path.abspath(os.path.dirname(__file__)))[0]
sentry = Sentry()

line_log = logging.getLogger("line")
order_log = logging.getLogger("order")
kefu_log = logging.getLogger("kefu")
access_log = logging.getLogger("access")


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
    stdout_fhd.setLevel(logging.DEBUG)
    stdout_fhd.setFormatter(fmt)
    for logger in [line_log, order_log, kefu_log, access_log]:
        logger.setLevel(logging.DEBUG)
        s = logger.name
        f = "logs/%s_%s.log" % (s, server_type)
        file_hd = TimedRotatingFileHandler(os.path.join(BASE_DIR, f),
                                           when='D', interval=1)
        file_hd.setLevel(logging.INFO)
        file_hd.setFormatter(fmt)
        logger.addHandler(stdout_fhd)
        logger.addHandler(file_hd)


def setup_app(config_name, server_type="api"):
    servers = {
        "api": setup_api_app,
        "admin": setup_admin_app,
    }
    app = servers[server_type](config_name)

    rset = app.config["REDIS_SETTIGNS"]["SESSION"]
    r = redis.Redis(host=rset["host"], port=rset["port"], db=rset["db"])
    app.session_interface = RedisSessionInterface(redis=r)

    sentry.init_app(app)
    init_logging(app, server_type)
    return app


def setup_api_app(config_name):
    app = Flask(__name__)
    config_name = "api_%s" % config_name
    app.config.from_object(config[config_name])
    config[config_name].init_app(app)
    print ">>> run api server, use", config[config_name].__name__

    mail.init_app(app)
    db.init_app(app)
    init_celery(app)

    from api import api as main_blueprint
    app.register_blueprint(main_blueprint)
    app.secret_key = 'A0Zr98j/3yX R~XHH!jmN]LWX/,?RT'
    return app


def setup_admin_app(config_name):
    config_name = "admin_%s" % config_name
    app = Flask(__name__)
    app.config.from_object(config[config_name])
    config[config_name].init_app(app)
    print ">>> run admin server, use", config[config_name].__name__

    mail.init_app(app)
    db.init_app(app)
    login_manager.init_app(app)
    init_celery(app)

    from admin import admin as admin_blueprint
    app.register_blueprint(admin_blueprint)
    app.secret_key = 'A0Zr98j/3yX R~XHH!jmN]LWX/,?RT'
    return app
