# -*- coding:utf-8 -*-
import os
import random

from flask.ext.testing import TestCase
from app.constants import *
from app import setup_app
from app.models import ScqcpRebot, Order

class RebotTestCase(TestCase):
    def create_app(self):
        app = setup_app()
        app.config['TESTING'] = True
        return app

    def test_login(self):
        accounts = SOURCE_INFO[SOURCE_SCQCP]["accounts"]
        tele = random.choice(accounts.keys())
        rebot = ScqcpRebot.objects.get(telephone=tele)

        passwd = rebot.password
        rebot.password = "errorpawd"
        try:
            self.assertNotEqual(rebot.login(), "OK")
        finally:
            rebot.modify(password=passwd)
        self.assertEqual(rebot.login(), "OK")
