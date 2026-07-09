"""
Payments models — gateway-agnostic payment tracking (SDD §16.13).

The Payment model records every transaction attempt. The actual gateway
integration (M-Pesa, eCitizen, Visa/MC) lives in gateways.py as adapter
classes. To add a new provider, just create a new adapter — no model changes.
"""
from django.conf import settings
from django.db import models
from django.utils.translation import gettext_lazy as _

from apps.commerce.models import Order
from core.models import BaseModel


class Payment(BaseModel):
    """Tracks a single payment attempt for an order."""

    class Provider(models.TextChoices):
        MPESA = "mpesa", _("M-Pesa")
        ECITIZEN = "ecitizen", _("eCitizen")
        VISA = "visa", _("Visa")
        MASTERCARD = "mastercard", _("Mastercard")
        MOCK = "mock", _("Mock (Testing)")

    class Status(models.TextChoices):
        INITIATED = "initiated", _("Initiated")
        PENDING = "pending", _("Pending")
        COMPLETED = "completed", _("Completed")
        FAILED = "failed", _("Failed")
        REFUNDED = "refunded", _("Refunded")

    order = models.ForeignKey(
        Order,
        on_delete=models.PROTECT,
        related_name="payments",
    )
    provider = models.CharField(
        max_length=20,
        choices=Provider.choices,
        db_index=True,
    )
    status = models.CharField(
        max_length=20,
        choices=Status.choices,
        default=Status.INITIATED,
        db_index=True,
    )
    amount = models.DecimalField(max_digits=10, decimal_places=2)
    currency = models.CharField(max_length=3, default="KES")
    transaction_id = models.CharField(
        max_length=255,
        blank=True,
        db_index=True,
        help_text=_("External transaction ID from the payment provider."),
    )
    provider_response = models.JSONField(
        default=dict,
        blank=True,
        help_text=_("Raw response from the payment gateway for debugging."),
    )
    paid_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        db_table = "payments"
        ordering = ["-created_at"]

    def __str__(self):
        return f"Payment {self.id} — {self.provider} — {self.status}"
