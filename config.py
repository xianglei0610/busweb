# -*- coding:utf-8 -*-
import os
basedir = os.path.abspath(os.path.dirname(__file__))


class Config:
    DEBUG = False
    PRESERVE_CONTEXT_ON_EXCEPTION = False

    # mail config
    MAIL_SERVER = 'smtp.exmail.qq.com'
    MAIL_PORT = 587
    MAIL_USE_TLS = True
    MAIL_USERNAME = 'dg@12308.com'
    MAIL_PASSWORD = 'PY12dg'

    # celery config
    CELERY_BROKER_URL = 'redis://localhost:6379/10'
    CELERY_RESULT_BACKEND = 'redis://localhost:6379/11'
    CELERY_TASK_SERIALIZER = 'pickle'
    CELERY_ACCEPT_CONTENT = ['pickle', 'json', 'msgpack', 'yaml']

    PERMANENT_SESSION_LIFETIME = 24*60*60   # session有效期

    # redis config
    REDIS_HOST = "localhost"
    REDIS_PORT = 6379
    REDIS_SETTIGNS = {
        "SESSION": {
            "host": REDIS_HOST,
            "port": REDIS_PORT,
            "db": 9,
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

    CRAWL_MONGODB_SETTINGS = {
        'db': 'crawl12308',
        'host': 'localhost',
        'port': 27017,
    }

    @staticmethod
    def init_app(app):
        pass


class ApiDevConfig(Config):

    MAIL_SERVER = 'smtp.exmail.qq.com'
    MAIL_PORT = 587
    MAIL_USE_TLS = True
    MAIL_USERNAME = os.environ.get('MAIL_USERNAME')
    MAIL_PASSWORD = os.environ.get('MAIL_PASSWORD')

    SENTRY_DSN = "http://b611fc0179bc4950862f510e0f0b70b0:c4933230a2314e9c81f11fd09004444c@112.74.132.104:9000/2"
    CELERY_SENTRY_DSN = "http://e883e9ca535c4e9a89a740f81d678d04:b58e45eb0dd84b5884d70b8674d433fb@112.74.132.104:9000/7"


    MONGODB_SETTINGS = {
        'db': 'web12308',
        'host': '192.168.1.202',
        'port': 27017,
    }

    CRAWL_MONGODB_SETTINGS = {
        'db': 'crawl12308',
        'host': '192.168.1.202',
        'port': 27017,
    }


class ApiProdConfig(Config):
    SENTRY_DSN = "http://0ab2a036d18f489d94a8dae384a3ea58:28e30d019c5a410696bad6e100efea5f@112.74.132.104:9000/4"
    CELERY_SENTRY_DSN = "http://fb965560e74c498b9d09ce05577592b4:c7cccc3c58f649b7aea3cbac59993b61@112.74.132.104:9000/6"


class ApiLocalConfig(Config):

    DEBUG = True


class AdminDevConfig(ApiDevConfig):
    SENTRY_DSN = "http://2cc0ca97e2e5456796de23c1ece3f9f3:6b99a5fea50c434182759494b9be569a@112.74.132.104:9000/3"


class AdminProdConfig(ApiProdConfig):
    SENTRY_DSN = "http://c9469ae07fe94fdc842adb3b1e0bae52:f62e2e4d316c458c8a1d462a33dda573@112.74.132.104:9000/5"


class AdminLocalConfig(ApiLocalConfig):

    DEBUG = True

config = {
    'api_local': ApiLocalConfig,
    'api_dev': ApiDevConfig,
    'api_prod': ApiProdConfig,

    'admin_local': AdminLocalConfig,
    'admin_dev': AdminDevConfig,
    'admin_prod': AdminProdConfig,
}
