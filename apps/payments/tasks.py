"""
Async email delivery for payments. Celery is optional — see
apps/ingestion/tasks.py for the same inline-execution shim when no
broker is configured (CELERY_TASK_ALWAYS_EAGER).

Errors are logged, never raised: a broken mailbox must not undo a
completed payment or make the API response fail.
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
def send_payment_success_email(order_id: str):
    from apps.commerce.models import Order

    from .emails import send_payment_success_email as _send

    order = Order.objects.select_related("user").get(id=order_id)
    try:
        _send(order)
        logger.info(
            "EMAIL SENT payment-success to=%s order=%s", order.user.email, order.order_number
        )
    except Exception:  # noqa: BLE001
        logger.exception("EMAIL FAILED payment-success order=%s", order.order_number)


@shared_task
def send_payment_failed_email(order_id: str):
    from apps.commerce.models import Order

    from .emails import send_payment_failed_email as _send

    order = Order.objects.select_related("user").get(id=order_id)
    try:
        _send(order)
        logger.info(
            "EMAIL SENT payment-failed to=%s order=%s", order.user.email, order.order_number
        )
    except Exception:  # noqa: BLE001
        logger.exception("EMAIL FAILED payment-failed order=%s", order.order_number)
