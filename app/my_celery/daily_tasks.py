from my_celery.base_celery import celery
from api.party.party import clean_db, clean_party
from api.session.daily import award_prev_daily_challenge_coins, create_daily
from celery.schedules import crontab

@celery.task
def clean_db_task():
    """Cleans up the database"""
    clean_db()
@celery.task
def clean_party_task():
    """Cleans up the party database"""
    clean_party()

@celery.task
def create_daily_task():
    """Creates a new daily challenge"""
    create_daily()

@celery.task
def award_prev_daily_challenge_coins_task():
    """Awards coins for the previous daily challenge"""
    award_prev_daily_challenge_coins()

def init_daily_tasks(celery):    
    celery.conf.beat_schedule = {
        'clean-db-midnight': {
            'task': 'my_celery.daily_tasks.clean_db_task',
            'schedule': crontab(hour=0, minute=0),  # midnight UTC
        },
        'create-daily-midnight': {
            'task': 'my_celery.daily_tasks.create_daily_task',
            'schedule': crontab(hour=0, minute=0),
        },
        'award-coins-midnight': {
            'task': 'my_celery.daily_tasks.award_prev_daily_challenge_coins_task',
            'schedule': crontab(hour=0, minute=0),
        },
        'clean-parties-midnight': {
            'task': 'my_celery.daily_tasks.clean_party_task',
            'schedule': crontab(hour=0, minute=0),
        },
    }