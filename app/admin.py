from flask import request, redirect, url_for, flash, session
from sqlalchemy import inspect
from flask_admin.contrib.sqla import ModelView
from flask_admin import Admin, AdminIndexView, expose
from api.auth.auth import login_required
from api.auth.routes import bcrypt

from models.db import db
from models.user import User

class ChildView(ModelView):
    column_display_pk = True
    column_hide_backrefs = False
    def __init__(self,model):
        self.column_filters = [c_attr.key for c_attr in inspect(model).mapper.column_attrs]
        super().__init__(model,db.session)
    
    def is_accessible(self):
        return session.get('is_admin', False)

    def inaccessible_callback(self, name, **kwargs):
        flash("Access Denied!", "danger")
        return redirect(url_for('admin.index'))

class MyAdminIndexView(AdminIndexView):
    @expose('/')
    def index(self):
        if not session.get('is_admin', False):
            return self.render('admin_login.html')
        return super(MyAdminIndexView, self).index()

    @expose('/login', methods=['POST'])
    def login(self):
        username = request.form['username']
        password = request.form['password']
        user = User.query.filter_by(username=username).first()

        if user and bcrypt.check_password_hash(user.password, password) and user.is_admin:
            session['user'] = user.username
            session['is_admin'] = user.is_admin
            flash('Login Successful!', 'success')
            return redirect(url_for('admin.index'))
        flash('Invalid credentials', 'danger')
        return redirect(url_for('admin.index'))

    @expose('/logout')
    def logout(self):
        session.clear()
        flash('Logged out successfully', 'success')
        return redirect(url_for('admin.index'))


admin = Admin(name="My Admin Panel",index_view=MyAdminIndexView(),template_mode="bootstrap4")
for model in db.Model.__subclasses__():
    admin.add_view(ChildView(model))