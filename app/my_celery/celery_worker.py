import eventlet
eventlet.monkey_patch(socket=True)

from my_celery.base_celery import init_celery
from app import app

celery = init_celery(app)