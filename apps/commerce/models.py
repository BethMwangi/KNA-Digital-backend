"""
Commerce models — Licences, Pricing, Cart, Orders (SDD §16.8–§16.12).

Design decisions:
- License defines usage rights (Editorial, Commercial, etc.).
- AssetPrice links a DigitalAsset to a License with a price in KES.
- ShoppingCart is one-per-user, lazy-created on first add.
- Order is immutable after placement; state machine tracks fulfilment.
"""
import uuid

from django.conf import settings
from django.db import models
from django.utils.translation import gettext_lazy as _

from apps.assets.models import DigitalAsset
from core.models import BaseModel


# ------------------------------------------------------------------ #
# License & Pricing
# ------------------------------------------------------------------ #
class License(BaseModel):
    """Usage rights tier — e.g. Editorial, Commercial, Extended."""

    name = models.CharField(max_length=100, unique=True)
    slug = models.SlugField(max_length=100, unique=True)
    description = models.TextField(blank=True)
    allows_commercial = models.BooleanField(default=False)
    allows_modification = models.BooleanField(default=False)
    max_print_run = models.PositiveIntegerField(
        null=True,
        blank=True,
        help_text=_("Max copies for print use. NULL = unlimited."),
    )

    class Meta:
        db_table = "licenses"

    def __str__(self):
        return self.name


class AssetPrice(BaseModel):
    """
    Links an asset to a license with a price.
    One asset can have multiple prices (one per license tier).
    """

    asset = models.ForeignKey(
        DigitalAsset,
        on_delete=models.CASCADE,
        related_name="prices",
    )
    license = models.ForeignKey(
        License,
        on_delete=models.PROTECT,
        related_name="prices",
    )
    amount = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        help_text=_("Price in KES."),
    )
    is_active = models.BooleanField(default=True)

    class Meta:
        db_table = "asset_prices"
        unique_together = ["asset", "license"]

    def __str__(self):
        return f"{self.asset.title} — {self.license.name}: KES {self.amount}"


# ------------------------------------------------------------------ #
# Shopping Cart
# ------------------------------------------------------------------ #
class ShoppingCart(BaseModel):
    """One cart per authenticated user; lazy-created."""

    user = models.OneToOneField(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="cart",
    )

    class Meta:
        db_table = "shopping_carts"

    def __str__(self):
        return f"Cart for {self.user.email}"

    @property
    def total(self):
        return sum(item.subtotal for item in self.items.all())

    @property
    def item_count(self):
        return self.items.count()


class CartItem(BaseModel):
    """A single line in the shopping cart."""

    cart = models.ForeignKey(
        ShoppingCart,
        on_delete=models.CASCADE,
        related_name="items",
    )
    asset_price = models.ForeignKey(
        AssetPrice,
        on_delete=models.CASCADE,
        related_name="cart_items",
    )

    class Meta:
        db_table = "cart_items"
        unique_together = ["cart", "asset_price"]

    def __str__(self):
        return f"{self.asset_price.asset.title} ({self.asset_price.license.name})"

    @property
    def subtotal(self):
        return self.asset_price.amount


# ------------------------------------------------------------------ #
# Orders
# ------------------------------------------------------------------ #
class Order(BaseModel):
    """Immutable record of a completed purchase."""

    class Status(models.TextChoices):
        PENDING = "pending", _("Pending Payment")
        PAID = "paid", _("Paid")
        FAILED = "failed", _("Payment Failed")
        REFUNDED = "refunded", _("Refunded")
        CANCELLED = "cancelled", _("Cancelled")

    order_number = models.CharField(max_length=50, unique=True, db_index=True)
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name="orders",
    )
    status = models.CharField(
        max_length=20,
        choices=Status.choices,
        default=Status.PENDING,
        db_index=True,
    )
    subtotal = models.DecimalField(max_digits=10, decimal_places=2)
    tax = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    total = models.DecimalField(max_digits=10, decimal_places=2)
    currency = models.CharField(max_length=3, default="KES")
    notes = models.TextField(blank=True)

    class Meta:
        db_table = "orders"
        ordering = ["-created_at"]

    def __str__(self):
        return f"Order {self.order_number} — {self.status}"


class OrderItem(BaseModel):
    """Snapshot of what was purchased — price is frozen at purchase time."""

    order = models.ForeignKey(
        Order,
        on_delete=models.CASCADE,
        related_name="items",
    )
    asset = models.ForeignKey(
        DigitalAsset,
        on_delete=models.PROTECT,
        related_name="order_items",
    )
    license = models.ForeignKey(
        License,
        on_delete=models.PROTECT,
        related_name="order_items",
    )
    price_at_purchase = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        help_text=_("Frozen price at the time of purchase."),
    )
    asset_title_snapshot = models.CharField(
        max_length=255,
        help_text=_("Asset title at time of purchase, in case it changes later."),
    )

    class Meta:
        db_table = "order_items"

    def __str__(self):
        return f"{self.asset_title_snapshot} in Order {self.order.order_number}"
