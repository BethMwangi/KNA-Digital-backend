"""Commerce serializers — Cart, Orders, Licenses, Pricing."""
import uuid

from django.db import transaction
from rest_framework import serializers

from apps.assets.serializers import DigitalAssetListSerializer

from .models import (
    AssetPrice,
    CartItem,
    License,
    Order,
    OrderItem,
    ShoppingCart,
)


# ------------------------------------------------------------------ #
# License & Pricing
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


class AssetPriceSerializer(serializers.ModelSerializer):
    license = LicenseSerializer(read_only=True)
    asset_title = serializers.CharField(source="asset.title", read_only=True)

    class Meta:
        model = AssetPrice
        fields = ["id", "asset", "asset_title", "license", "amount", "is_active"]


# ------------------------------------------------------------------ #
# Cart
# ------------------------------------------------------------------ #
class CartItemSerializer(serializers.ModelSerializer):
    asset_price = AssetPriceSerializer(read_only=True)
    subtotal = serializers.DecimalField(max_digits=10, decimal_places=2, read_only=True)

    class Meta:
        model = CartItem
        fields = ["id", "asset_price", "subtotal", "created_at"]


class CartDetailSerializer(serializers.ModelSerializer):
    items = CartItemSerializer(many=True, read_only=True)
    total = serializers.DecimalField(max_digits=10, decimal_places=2, read_only=True)
    item_count = serializers.IntegerField(read_only=True)

    class Meta:
        model = ShoppingCart
        fields = ["id", "items", "total", "item_count"]


class AddToCartSerializer(serializers.Serializer):
    """Accepts an asset_price_id to add to the user's cart."""

    asset_price_id = serializers.UUIDField()

    def validate_asset_price_id(self, value):
        try:
            price = AssetPrice.objects.get(id=value, is_active=True)
        except AssetPrice.DoesNotExist:
            raise serializers.ValidationError("Invalid or inactive asset price.")
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
        except ShoppingCart.DoesNotExist:
            raise serializers.ValidationError({"cart": "Your cart is empty."})

        cart_items = cart.items.select_related("asset_price__asset", "asset_price__license").all()
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
                    asset=item.asset_price.asset,
                    license=item.asset_price.license,
                    price_at_purchase=item.asset_price.amount,
                    asset_title_snapshot=item.asset_price.asset.title,
                )
                for item in cart_items
            ]
            OrderItem.objects.bulk_create(order_items)

            # Clear the cart after checkout
            cart_items.delete()

        return order
