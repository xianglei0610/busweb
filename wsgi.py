#!/usr/bin/env python
# -*- coding:utf-8 *-*
import os

from app import setup_app
app = setup_app(os.getenv('FLASK_CONFIG') or 'prod',
                os.getenv('FLASK_SERVER') or 'api')
