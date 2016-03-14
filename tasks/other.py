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
