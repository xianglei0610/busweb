# -*- coding:utf-8 -*-
import os
basedir = os.path.abspath(os.path.dirname(__file__))


class Config:
    DEBUG = False
    PRESERVE_CONTEXT_ON_EXCEPTION = False

    MAIL_SERVER = 'smtp.exmail.qq.com'
    MAIL_PORT = 587
    MAIL_USE_TLS = True
    MAIL_USERNAME = 'xiangleilei@12308.com'
    MAIL_PASSWORD = 'Lei710920610'

    # celery config
    CELERY_BROKER_URL = 'redis://localhost:6379/10'
    CELERY_RESULT_BACKEND = 'redis://localhost:6379/11'
    CELERY_TASK_SERIALIZER = 'pickle'
    CELERY_ACCEPT_CONTENT = ['pickle', 'json', 'msgpack', 'yaml']

    @staticmethod
    def init_app(app):
        pass

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


class ApiDevConfig(Config):

    MAIL_SERVER = 'smtp.googlemail.com'
    MAIL_PORT = 587
    MAIL_USE_TLS = True
    MAIL_USERNAME = os.environ.get('MAIL_USERNAME')
    MAIL_PASSWORD = os.environ.get('MAIL_PASSWORD')


class ApiProdConfig(Config):
    pass


class ApiLocalConfig(Config):

    DEBUG = True


class AdminDevConfig(Config):
    pass


class AdminProdConfig(Config):
    pass


class AdminLocalConfig(Config):

    DEBUG = True

config = {
    'api_local': ApiLocalConfig,
    'api_dev': ApiDevConfig,
    'api_prod': ApiProdConfig,

    'admin_local': AdminLocalConfig,
    'admin_dev': AdminDevConfig,
    'admin_prod': AdminProdConfig,
}
