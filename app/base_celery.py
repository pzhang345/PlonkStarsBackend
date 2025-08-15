from celery import Celery
from config import Config

celery = Celery(__name__, broker=Config.REDIS_URL, backend=Config.REDIS_URL)

def init_celery(app):
    class ContextTask(celery.Task):
        def __call__(self, *args, **kwargs):
            with app.app_context():
                return self.run(*args, **kwargs)

    celery.Task = ContextTask
    celery.conf.update(
        result_expires=3600
    )
    celery.autodiscover_tasks(['api.game.tasks'])
    return celery