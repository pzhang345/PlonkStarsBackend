import eventlet
eventlet.monkey_patch(socket=True)

from base_celery import init_celery
from app import app

celery = init_celery(app)