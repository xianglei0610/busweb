# -*- coding:utf-8 *-*
import sys
reload(sys)
sys.setdefaultencoding("utf-8")

from flask import Flask
from flask.ext.mail import Mail
from flask.ext.mongoengine import MongoEngine
from flask.ext.login import LoginManager
from config import config
from celery import Celery, platforms
platforms.C_FORCE_ROOT = True

mail = Mail()
db = MongoEngine()
celery = Celery(__name__, broker="redis://localhost:6379/10")
login_manager = LoginManager()


def init_celery(app):
    TaskBase = celery.Task
    celery.conf.update(app.config)

    class ContextTask(TaskBase):
        abstract = True

        def __call__(self, *args, **kwargs):
            with app.app_context():
                return TaskBase.__call__(self, *args, **kwargs)
    celery.Task = ContextTask


def setup_app(config_name, server_type="api"):
    servers = {
        "api": setup_api_app,
        "admin": setup_admin_app,
    }
    return servers[server_type](config_name)


def setup_api_app(config_name):
    print "run api server"
    app = Flask(__name__)
    config_name = "api_%s" % config_name
    app.config.from_object(config[config_name])
    config[config_name].init_app(app)
    print "use config", config[config_name].__name__

    mail.init_app(app)
    db.init_app(app)
    init_celery(app)

    from api import api as main_blueprint
    app.register_blueprint(main_blueprint)
    app.secret_key = 'A0Zr98j/3yX R~XHH!jmN]LWX/,?RT'
    return app


def setup_admin_app(config_name):
    print "run admin server"
    config_name = "admin_%s" % config_name
    app = Flask(__name__)
    app.config.from_object(config[config_name])
    config[config_name].init_app(app)
    print "use config", config[config_name].__name__

    mail.init_app(app)
    db.init_app(app)
    login_manager.init_app(app)
    init_celery(app)

    from admin import admin as admin_blueprint
    app.register_blueprint(admin_blueprint)
    app.secret_key = 'A0Zr98j/3yX R~XHH!jmN]LWX/,?RT'
    return app
