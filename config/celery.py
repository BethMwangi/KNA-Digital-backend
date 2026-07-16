"""
Celery application. Broker is RabbitMQ (CELERY_BROKER_URL); tasks are
autodiscovered from each app's tasks.py.

Run a worker locally with:
    celery -A config worker -l info
(docker compose starts one as the `worker` service.)

Where no worker exists (e.g. single-process deploys), set
CELERY_TASK_ALWAYS_EAGER=True and tasks execute inline instead.
"""

import os

from celery import Celery

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings.development")

app = Celery("kna")
app.config_from_object("django.conf:settings", namespace="CELERY")
app.autodiscover_tasks()
