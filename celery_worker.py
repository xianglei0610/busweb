
# -*- coding:utf-8 *-*
import os
import sys
reload(sys)
sys.setdefaultencoding("utf-8")
import logging
from app import setup_app, celery
from raven import Client
from raven.contrib.celery import register_signal, register_logger_signal

app = setup_app(os.getenv('FLASK_CONFIG') or 'local',
                os.getenv('FLASK_SERVER') or 'api')


dsn = app.config["CELERY_SENTRY_DSN"]
if dsn:
    client = Client(dsn)
    # register a custom filter to filter out duplicate logs
    register_logger_signal(client)
    # hook into the Celery error handler
    register_signal(client)
    # The register_logger_signal function can also take an optional argument
    # `loglevel` which is the level used for the handler created.
    # Defaults to `logging.ERROR`
    register_logger_signal(client, loglevel=logging.INFO)
