"""Load the Celery app on Django startup so @shared_task binds to it.
Guarded so slim environments without celery installed still boot."""

try:
    from .celery import app as celery_app

    __all__ = ["celery_app"]
except ImportError:  # celery not installed — tasks.py shims .delay() inline
    celery_app = None
