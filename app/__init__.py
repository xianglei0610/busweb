# -*- coding:utf-8 *-*

from flask import Flask
from flask.ext.mail import Mail
from config import config

mail = Mail()


def create_app(config_name):
    app = Flask(__name__)
    app.config.from_object(config[config_name])
    config[config_name].init_app(app)

    mail.init_app(app)

    # attach routes and custom error pages here
    import scqcp as scqcp_blueprint
    app.register_blueprint(scqcp_blueprint)

    return app
