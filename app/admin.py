from sqlalchemy import inspect
from flask_admin.contrib.sqla import ModelView
from flask_admin import Admin
from models import db,User

from sqlalchemy import inspect

class ChildView(ModelView):
    column_display_pk = True # optional, but I like to see the IDs in the list
    column_hide_backrefs = False
    def __init__(self,database):
        super().__init__(database,db.session)
        self.column_list = [c_attr.key for c_attr in inspect(database).mapper.column_attrs]



admin = Admin(name='My Admin Panel', template_mode='bootstrap4')

for database in db.Model.__subclasses__():
    admin.add_view(ChildView(database))