#!/usr/bin/env python
# -*- coding:utf-8 *-*
import datetime

from flask import Flask

from flask.ext import admin
from flask.ext.mongoengine import MongoEngine
from flask.ext.admin.form import rules
from flask.ext.admin.contrib.mongoengine import ModelView

from app.models import Line, Order 

# Create application
app = Flask(__name__)

# Create dummy secrey key so we can use sessions
app.config['SECRET_KEY'] = '123456790'
app.config['MONGODB_SETTINGS'] = {'DB': 'testing'}

# Create models
db = MongoEngine()
db.init_app(app)




class OrderView(ModelView):
#     column_list = ('order_no', 'status')
    column_labels = dict(name='order_no', status=u'状态')
    list_template = 'list.html'
# #     edit_template = 'edit.html'
#     can_view_details = True
#     can_edit = True
    pass
#     column_filters = ['order_no', 'status', 'order_from', 'order_price', 'create_date_time']
# 
#     column_searchable_list = ('order_no', 'status')

#     form_ajax_refs = {
#         'riders': {
#             'fields': ['name']
#         }
#     }







class ScqcpOrderView(ModelView):
     pass
#     column_filters = ['name', 'telephone']
 
#     column_searchable_list = ('name',)




# Flask views
@app.route('/')
def index():
    return '<a href="/admin/">Click me to get to Admin!</a>'


if __name__ == '__main__':
    # Create admin
    admin = admin.Admin(app, 'Example: MongoEngine')

    # Add views
    admin.add_view(OrderView(Order))
#     admin.add_view(TodoView(Todo))
#     admin.add_view(ModelView(Tag))
#     admin.add_view(PostView(Post))
#     admin.add_view(ModelView(File))
#     admin.add_view(ModelView(Image))

    # Start app
    app.run(host='0.0.0.0',port=8000,debug=True)
