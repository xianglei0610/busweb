# -*- coding:utf-8 -*-
from flask.ext.mail import Message
from app import mail
from app import config


def send_email(subject, sender, recipients, text_body, html_body):
    if config.DEBUG:
        return
    msg = Message(subject, sender=sender, recipients=recipients)
    msg.body = text_body
    msg.html = html_body
    mail.send(msg)
