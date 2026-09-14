web: gunicorn --bind 0.0.0.0:${PORT:-5000} --workers ${WEB_CONCURRENCY:-1} --threads ${WEB_THREADS:-2} --timeout ${WEB_TIMEOUT:-120} app:app
worker: celery -A services.celery_app:celery_app worker --loglevel=${CELERY_LOG_LEVEL:-INFO}
beat: celery -A services.celery_app:celery_app beat --loglevel=${CELERY_LOG_LEVEL:-INFO}
