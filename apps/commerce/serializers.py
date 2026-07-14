"""Commerce serializers — Licenses, Cart, Orders."""

import uuid

from django.db import transaction
from rest_framework import serializers

from apps.assets.models import DigitalAsset
from apps.assets.serializers import public_variant_url

from .models import (
    CartItem,
    License,
    Order,
    OrderItem,
    ShoppingCart,
)


# ------------------------------------------------------------------ #
# License — usage-purpose the buyer picks at checkout, never priced.
# ------------------------------------------------------------------ #
class LicenseSerializer(serializers.ModelSerializer):
    class Meta:
        model = License
        fields = [
            "id",
            "name",
            "slug",
            "description",
            "allows_commercial",
            "allows_modification",
            "max_print_run",
        ]


# ------------------------------------------------------------------ #
# Cart
# ------------------------------------------------------------------ #
class CartAssetSerializer(serializers.ModelSerializer):
    """Lightweight asset summary for a cart line — enough to render the row."""

    thumbnail = serializers.SerializerMethodField()

    def get_thumbnail(self, obj):
        return public_variant_url(obj, "thumbnail") or public_variant_url(obj, "preview")

    class Meta:
        model = DigitalAsset
        fields = ["id", "asset_number", "title", "thumbnail", "price"]


class CartItemSerializer(serializers.ModelSerializer):
    asset = CartAssetSerializer(read_only=True)
    license = LicenseSerializer(read_only=True)
    subtotal = serializers.DecimalField(max_digits=10, decimal_places=2, read_only=True)

    class Meta:
        model = CartItem
        fields = ["id", "asset", "license", "subtotal", "created_at"]


class CartDetailSerializer(serializers.ModelSerializer):
    items = CartItemSerializer(many=True, read_only=True)
    total = serializers.DecimalField(max_digits=10, decimal_places=2, read_only=True)
    item_count = serializers.IntegerField(read_only=True)

    class Meta:
        model = ShoppingCart
        fields = ["id", "items", "total", "item_count"]


class AddToCartSerializer(serializers.Serializer):
    """Accepts the asset to buy and the usage license the buyer declares."""

    asset_id = serializers.UUIDField()
    license_id = serializers.UUIDField()

    def validate_asset_id(self, value):
        try:
            asset = DigitalAsset.objects.get(id=value)
        except DigitalAsset.DoesNotExist as err:
            raise serializers.ValidationError("Asset not found.") from err
        if asset.price is None:
            raise serializers.ValidationError("This asset isn't priced yet.")
        return value

    def validate_license_id(self, value):
        if not License.objects.filter(id=value).exists():
            raise serializers.ValidationError("Invalid license.")
        return value


# ------------------------------------------------------------------ #
# Orders
# ------------------------------------------------------------------ #
class OrderItemSerializer(serializers.ModelSerializer):
    class Meta:
        model = OrderItem
        fields = [
            "id",
            "asset",
            "asset_title_snapshot",
            "license",
            "price_at_purchase",
        ]


class OrderSerializer(serializers.ModelSerializer):
    items = OrderItemSerializer(many=True, read_only=True)

    class Meta:
        model = Order
        fields = [
            "id",
            "order_number",
            "status",
            "subtotal",
            "tax",
            "total",
            "currency",
            "notes",
            "items",
            "created_at",
            "updated_at",
        ]


class CheckoutSerializer(serializers.Serializer):
    """
    Creates an Order from the current cart contents.
    The cart is cleared after a successful order is placed.
    """

    notes = serializers.CharField(required=False, default="", allow_blank=True)

    def create(self, validated_data):
        user = self.context["request"].user
        try:
            cart = ShoppingCart.objects.get(user=user)
        except ShoppingCart.DoesNotExist as err:
            raise serializers.ValidationError({"cart": "Your cart is empty."}) from err

        cart_items = cart.items.select_related("asset", "license").all()
        if not cart_items.exists():
            raise serializers.ValidationError({"cart": "Your cart is empty."})

        subtotal = sum(item.subtotal for item in cart_items)
        tax = 0  # Phase One: tax calculation placeholder
        total = subtotal + tax

        with transaction.atomic():
            order = Order.objects.create(
                order_number=f"KNA-{uuid.uuid4().hex[:10].upper()}",
                user=user,
                subtotal=subtotal,
                tax=tax,
                total=total,
                notes=validated_data.get("notes", ""),
            )

            order_items = [
                OrderItem(
                    order=order,
                    asset=item.asset,
                    license=item.license,
                    price_at_purchase=item.asset.price,
                    asset_title_snapshot=item.asset.title,
                )
                for item in cart_items
            ]
            OrderItem.objects.bulk_create(order_items)

            # Clear the cart after checkout
            cart_items.delete()

        return order
