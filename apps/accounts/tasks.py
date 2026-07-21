"""
Async delivery for auth emails (verification, password reset).

Why async: these used to run synchronously inside the register/
forgot-password request. When the email provider is slow or blocked
(confirmed: Render drops outbound SMTP, causing a 30s hang and a 500 on
register — see core/email_backends.py), that took the whole request
down with it, even though the user account was already created. Moving
the send off the request path means registration/reset always succeeds
immediately regardless of email provider health; the email arrives
moments later.

Celery is optional — same inline-execution shim as apps/ingestion/tasks.py
and apps/payments/tasks.py when no broker is configured
(CELERY_TASK_ALWAYS_EAGER, default True).
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
def send_verification_email_task(user_id: str):
    from .models import User
    from .tokens import send_verification_email

    user = User.objects.filter(id=user_id).first()
    if user is None:
        return
    try:
        send_verification_email(user)
        logger.info("EMAIL SENT verification to=%s", user.email)
    except Exception:  # noqa: BLE001
        logger.exception("EMAIL FAILED verification to=%s", user.email)


@shared_task
def send_password_reset_email_task(user_id: str):
    from .models import User
    from .tokens import send_password_reset_email

    user = User.objects.filter(id=user_id).first()
    if user is None:
        return
    try:
        send_password_reset_email(user)
        logger.info("EMAIL SENT password-reset to=%s", user.email)
    except Exception:  # noqa: BLE001
        logger.exception("EMAIL FAILED password-reset to=%s", user.email)
