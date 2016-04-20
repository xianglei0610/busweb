# -*- coding:utf-8 -*-
import os
basedir = os.path.abspath(os.path.dirname(__file__))


class Config:
    DEBUG = False
    PRESERVE_CONTEXT_ON_EXCEPTION = False

    # mail config
    MAIL_SERVER = 'smtp.163.com'
    MAIL_PORT = 25
    MAIL_USE_TLS = True
    MAIL_USERNAME = '17095218904@163.com'
    MAIL_PASSWORD = 'b123456'

    # celery config
    CELERY_BROKER_URL = 'redis://localhost:6379/10'
    CELERY_RESULT_BACKEND = 'redis://localhost:6379/11'
    CELERY_TASK_SERIALIZER = 'pickle'
    CELERY_ACCEPT_CONTENT = ['pickle', 'json', 'msgpack', 'yaml']
    CELERY_IMPORTS=("tasks")

    PERMANENT_SESSION_LIFETIME = 24 * 60 * 60   # session有效期

    # 方便网接口地址
    FANGBIAN_API_URL = "http://testapi.fangbian.com:6801/fbapi.asmx"
    # FANGBIAN_API_URL = "http://qcapi.fangbian.com/fbapi.asmx"

    # scrapyd 地址
    SCRAPYD_URLS = [
        "http://localhost:6800/schedule.json",
    ]

    # redis config
    REDIS_HOST = "localhost"
    REDIS_PORT = 6379
    REDIS_SETTIGNS = {
        "session": {
            "host": REDIS_HOST,
            "port": REDIS_PORT,
            "db": 9,
        },
        "order": {
            "host": REDIS_HOST,
            "port": REDIS_PORT,
            "db": 1,
        },
        "default": {
            "host": REDIS_HOST,
            "port": REDIS_PORT,
            "db": 0,
        },
    }

    # sentry config
    SENTRY_DSN = ""
    CELERY_SENTRY_DSN = ""

    MONGODB_SETTINGS = {
        'db': 'web12308',
        'host': 'localhost',
        'port': 27017,
    }

    @staticmethod
    def init_app(app):
        app.config["flask_profiler"] = {
            "enabled": False,
            "storage": {
                "engine": "mongodb",
                "MONGO_URL": "mongodb://%s" % app.config["MONGODB_SETTINGS"]["host"],
                "DATABASE": app.config["MONGODB_SETTINGS"]["db"],
                "COLLECTION": "flaskprofile",
            },
            "basicAuth": {
                "enabled": True,
                "username": "admin",
                "password": "profile@12308"
            }
        }


class ApiDevConfig(Config):

    # scrapyd 地址
    SCRAPYD_URLS = [
        "http://192.168.1.202:6800/schedule.json",
    ]

    MONGODB_SETTINGS = {
        'db': 'web12308',
        'host': '192.168.1.202',
        'port': 27017,
    }


class ApiProdConfig(Config):
    SENTRY_DSN = "http://1916f5873331434aa12af8cfef67bad5:647b983117a54618bdd2fb92ea91e486@120.27.150.94:9000/5"
    CELERY_SENTRY_DSN = "http://38d90342880f41aaa8f4b8eed11c79ca:25101a5e37a04df882e2ff9c10d64b08@120.27.150.94:9000/4"

    CELERY_BROKER_URL = 'redis://10.51.9.34:6379/10'
    CELERY_RESULT_BACKEND = 'redis://10.51.9.34:6379/11'

    # 方便网接口地址
    FANGBIAN_API_URL = "http://qcapi.fangbian.com/fbapi.asmx"

    # scrapyd 地址
    SCRAPYD_URLS = [
        "http://localhost:6800/schedule.json"
    ]

    # redis config
    REDIS_HOST = "10.51.9.34"
    REDIS_PORT = 6379
    REDIS_SETTIGNS = {
        "session": {
            "host": REDIS_HOST,
            "port": REDIS_PORT,
            "db": 9,
        },
        "order": {
            "host": REDIS_HOST,
            "port": REDIS_PORT,
            "db": 1,
        },
        "default": {
            "host": REDIS_HOST,
            "port": REDIS_PORT,
            "db": 0,
        },
    }

    MONGODB_SETTINGS = {
        'db': 'web12308',
        'host': '10.51.9.34',
        'port': 27017,
    }


class ApiLocalConfig(Config):

    DEBUG = True


class AdminDevConfig(ApiDevConfig):
    pass


class AdminProdConfig(ApiProdConfig):
    SENTRY_DSN = "http://eb323c77f19a4ffda4532bf8a4d5000f:ecdb186f84d5425a86844b3073796938@120.27.150.94:9000/6"


class AdminLocalConfig(ApiLocalConfig):

    DEBUG = True

config_mapping = {
    'api_local': ApiLocalConfig,
    'api_dev': ApiDevConfig,
    'api_prod': ApiProdConfig,

    'admin_local': AdminLocalConfig,
    'admin_dev': AdminDevConfig,
    'admin_prod': AdminProdConfig,
}
