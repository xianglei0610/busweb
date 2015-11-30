# -*- coding:utf-8 -*-
import os
basedir = os.path.abspath(os.path.dirname(__file__))


class Config:
    SECRET_KEY = os.environ.get('SECRET_KEY') or 'hard to guess string'

    @staticmethod
    def init_app(app):
        pass


class DevelopmentConfig(Config):
    DEBUG = True

    MAIL_SERVER = 'smtp.googlemail.com'
    MAIL_PORT = 587
    MAIL_USE_TLS = True
    MAIL_USERNAME = os.environ.get('MAIL_USERNAME')
    MAIL_PASSWORD = os.environ.get('MAIL_PASSWORD')


class ProductionConfig(Config):
    pass


class LocalConfig(Config):

    DEBUG = True
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

    CELERY_BROKER_URL='redis://localhost:6379',
    CELERY_RESULT_BACKEND='redis://localhost:6379'


config = {
    'local': LocalConfig,
    'dev': DevelopmentConfig,
    'prod': ProductionConfig,
    'default': LocalConfig
}
