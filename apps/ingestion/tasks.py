"""
Background tasks. Celery is optional — this deployment runs without a
broker, so the shim below makes .delay() execute inline (equivalent to
CELERY_TASK_ALWAYS_EAGER). If Celery is installed later, these become
real queued tasks with zero call-site changes.
"""

import logging

logger = logging.getLogger(__name__)

try:
    from celery import shared_task
except ImportError:  # no celery — run tasks inline

    def shared_task(*dargs, **dkwargs):
        def decorator(fn):
            fn.delay = fn
            return fn

        if dargs and callable(dargs[0]):
            return decorator(dargs[0])
        return decorator


@shared_task
def mirror_thumbnail(variant_id: str):
    """Copy an external thumbnail into our public bucket and repoint the
    variant (see mirroring.py). Safe to re-run; no-op once mirrored."""
    from .mirroring import mirror_variant

    mirror_variant(variant_id)
