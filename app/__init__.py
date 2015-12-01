# -*- coding:utf-8 *-*
import sys

from flask import Flask
from flask.ext.mail import Mail
from flask.ext.mongoengine import MongoEngine
from config import config

app = Flask(__name__)
mail = Mail()
db = MongoEngine()


reload(sys)
sys.setdefaultencoding("utf-8")


def setup_app(config_name):
    print "runser server in %s mode" % config_name
    app.config.from_object(config[config_name])
    config[config_name].init_app(app)

    mail.init_app(app)
    db.init_app(app)

    from main import main as main_blueprint
    app.register_blueprint(main_blueprint)
