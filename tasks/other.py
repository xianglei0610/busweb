#!/usr/bin/env python
# encoding: utf-8
from app.constants import *
from app import celery
from app.email import send_email
from flask import current_app


@celery.task(bind=True, ignore_result=True)
def async_send_email(self, subject, body):
    send_email(subject,
               current_app.config["MAIL_USERNAME"],
               ADMINS,
               "",
               body)


@celery.task(bind=True, ignore_result=True)
def check_add_proxy_ip(self, proxy_name, ipstr):
    from app.proxy import get_proxy
    consumer = get_proxy(proxy_name)
    consumer.on_producer_add(ipstr)


@celery.task(bind=True)
def check_remove_proxy_ip(self, proxy_name, ipstr):
    from app.proxy import get_proxy
    consumer = get_proxy(proxy_name)
    if not consumer.valid_proxy(ipstr):
        consumer.remove_proxy(ipstr)
        return "removed"
