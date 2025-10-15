from celery import Celery, signals
from config import Config
import ssl
from models.db import db

redis_ssl_url = Config.REDIS_URL + "/0?ssl_cert_reqs=CERT_NONE" if Config.REDIS_URL.startswith("rediss://") else Config.REDIS_URL

celery = Celery(__name__, broker=redis_ssl_url, backend=redis_ssl_url)

def init_celery(app):
    class ContextTask(celery.Task):
        def __call__(self, *args, **kwargs):
            with app.app_context():
                return self.run(*args, **kwargs)

    celery.Task = ContextTask
    
    celery.conf.update(
        result_expires=3600,
        timezone='UTC', 
        enable_utc=True
    )
    
    from my_celery.daily_tasks import init_daily_tasks
    init_daily_tasks(celery)
    
    if Config.REDIS_URL.startswith("rediss://"):
        celery.conf.update(
            broker_use_ssl = {"ssl_cert_reqs": ssl.CERT_NONE}
        )
    
    @signals.task_postrun.connect
    def cleanup_sessions(*args, **kwargs):
        with app.app_context():
            db.session.remove()
    
    celery.autodiscover_tasks(['api.game.tasks'])
    return celery


    