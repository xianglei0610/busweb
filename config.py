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

    PERMANENT_SESSION_LIFETIME = 30 * 60   # session有效期

    # 方便网接口地址
    FANGBIAN_API_URL = "http://testapi.fangbian.com:6801/fbapi.asmx"
    # FANGBIAN_API_URL = "http://qcapi.fangbian.com/fbapi.asmx"

    # scrapyd 地址
    SCRAPYD_URLS = [
        "http://10.24.243.168:6800/schedule.json",
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
        "line": {
            "host": REDIS_HOST,
            "port": REDIS_PORT,
            "db": 2,
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
    SENTRY_DSN = "http://da8f146ff18546018b40c126ad92912b:f99a13a0d2724219a81b83c1827d3541@120.27.150.94:9000/8"
    CELERY_SENTRY_DSN = "http://1eabb3c3d1f44c569f074540570335ce:8245e10562804a168bc3150f012a5f1c@120.27.150.94:9000/9"

    CELERY_BROKER_URL = 'redis://10.51.9.34:6379/10'
    CELERY_RESULT_BACKEND = 'redis://10.51.9.34:6379/11'

    # 方便网接口地址
    FANGBIAN_API_URL = "http://qcapi.fangbian.com/fbapi.asmx"

    # scrapyd 地址
    SCRAPYD_URLS = [
        "http://10.24.243.168:6800/schedule.json"
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
        "line": {
            "host": REDIS_HOST,
            "port": REDIS_PORT,
            "db": 2,
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
    SENTRY_DSN = "http://2d063c00755448e0810523c66e3c2ced:3ac419321eb3481d895da8b69ef882af@120.27.150.94:9000/7"


class AdminLocalConfig(ApiLocalConfig):

    DEBUG = True

config_mapping = {
    'api_local': ApiLocalConfig,
    'api_dev': ApiDevConfig,
    'api_prod': ApiProdConfig,

    'dashboard_local': AdminLocalConfig,
    'dashboard_dev': AdminDevConfig,
    'dashboard_prod': AdminProdConfig,
}
