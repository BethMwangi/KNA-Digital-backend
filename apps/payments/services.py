"""
Payment completion logic — shared by every gateway path (mock simulate
endpoint today; the real M-Pesa/eCitizen/card webhooks land on the same
functions once wired in, per gateways.py's adapter design).

Design rules, both load-bearing:
- Download entitlements are granted HERE, not at checkout. An order is
  just an intent to pay until a payment actually completes.
- Every path is idempotent (get_or_create for downloads, status guards
  before transitioning) because real gateway webhooks retry on timeout —
  a payment can legitimately be "completed" twice over the wire.
"""

import logging

from django.db import transaction
from django.utils import timezone

from apps.commerce.models import Order
from apps.downloads.models import Download

from .models import Payment

logger = logging.getLogger(__name__)


def complete_payment(payment: Payment, *, provider_response: dict | None = None) -> Payment:
    """Mark a payment COMPLETED, mark its order PAID, and grant download
    entitlements for every item on the order. Safe to call more than once
    for the same payment (webhook retries) — later calls are no-ops."""
    if payment.status == Payment.Status.COMPLETED:
        logger.info(
            "PAYMENT already completed, ignoring duplicate callback: payment=%s order=%s",
            payment.id,
            payment.order.order_number,
        )
        return payment

    with transaction.atomic():
        payment.status = Payment.Status.COMPLETED
        payment.paid_at = timezone.now()
        if provider_response is not None:
            payment.provider_response = provider_response
        payment.save(update_fields=["status", "paid_at", "provider_response", "updated_at"])

        order = payment.order
        order.status = Order.Status.PAID
        order.save(update_fields=["status", "updated_at"])

        granted, already_owned = 0, 0
        for item in order.items.select_related("asset", "license"):
            download, created = Download.objects.get_or_create(
                user=order.user,
                asset=item.asset,
                license=item.license,
                defaults={"order": order, "max_downloads": 5},
            )
            if created:
                granted += 1
            else:
                already_owned += 1

    logger.info(
        "PAYMENT COMPLETED payment=%s order=%s user=%s provider=%s amount=%s KES "
        "| downloads: %d granted, %d already owned",
        payment.id,
        order.order_number,
        order.user.email,
        payment.provider,
        payment.amount,
        granted,
        already_owned,
    )

    transaction.on_commit(lambda: _send_success_email(order.id))
    return payment


def fail_payment(payment: Payment, *, provider_response: dict | None = None) -> Payment:
    """Mark a payment FAILED. The order stays PENDING (not FAILED) so the
    customer can simply try again — same order, a new payment attempt —
    instead of losing the cart contents to a terminal state."""
    payment.status = Payment.Status.FAILED
    if provider_response is not None:
        payment.provider_response = provider_response
    payment.save(update_fields=["status", "provider_response", "updated_at"])

    logger.warning(
        "PAYMENT FAILED payment=%s order=%s user=%s provider=%s amount=%s KES — "
        "order stays pending, retry allowed",
        payment.id,
        payment.order.order_number,
        payment.order.user.email,
        payment.provider,
        payment.amount,
    )

    transaction.on_commit(lambda: _send_failure_email(payment.order.id))
    return payment


def _send_success_email(order_id) -> None:
    from .tasks import send_payment_success_email

    send_payment_success_email.delay(str(order_id))


def _send_failure_email(order_id) -> None:
    from .tasks import send_payment_failed_email

    send_payment_failed_email.delay(str(order_id))
