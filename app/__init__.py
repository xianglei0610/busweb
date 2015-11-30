# -*- coding:utf-8 *-*
import sys

from flask import Flask
from flask.ext.mail import Mail
from flask.ext.mongoengine import MongoEngine
from config import config
from celery import Celery

app = Flask(__name__)
mail = Mail()
db = MongoEngine()


reload(sys)
sys.setdefaultencoding("utf-8")


def make_celery(app):
    celery = Celery(app.import_name, broker=app.config['CELERY_BROKER_URL'])
    celery.conf.update(app.config)
    TaskBase = celery.Task
    class ContextTask(TaskBase):
        abstract = True
        def __call__(self, *args, **kwargs):
            with app.app_context():
                return TaskBase.__call__(self, *args, **kwargs)
    celery.Task = ContextTask
    return celery

def setup_app(config_name):
    print "runser server in %s mode" % config_name
    app.config.from_object(config[config_name])
    config[config_name].init_app(app)

    mail.init_app(app)
    db.init_app(app)
    celery = make_celery(app)


    # attach routes and custom error pages here
    from main import main as main_blueprint
    app.register_blueprint(main_blueprint)
