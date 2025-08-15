web: cd app && gunicorn --worker-class eventlet -w 1 --bind 0.0.0.0:$PORT app:app
worker: cd app && celery -A celery_worker.celery worker --loglevel=info