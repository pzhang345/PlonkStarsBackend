from sqlalchemy import inspect
from flask_admin.contrib.sqla import ModelView
from flask_admin import Admin

from models import db

class ChildView(ModelView):
    column_display_pk = True
    column_hide_backrefs = False
    def __init__(self,model):
        self.column_filters = [c_attr.key for c_attr in inspect(model).mapper.column_attrs]
        super().__init__(model,db.session)

admin = Admin(name='My Admin Panel',template_mode='bootstrap4')

for model in db.Model.__subclasses__():
    admin.add_view(ChildView(model))