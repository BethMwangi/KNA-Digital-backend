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
# Cart
# ------------------------------------------------------------------ #
class CartItemSerializer(serializers.ModelSerializer):
    asset = DigitalAssetListSerializer(read_only=True)
    subtotal = serializers.DecimalField(max_digits=10, decimal_places=2, read_only=True)

    class Meta:
        model = CartItem
        fields = ["id", "asset", "subtotal", "created_at"]


class CartDetailSerializer(serializers.ModelSerializer):
    items = CartItemSerializer(many=True, read_only=True)
    total = serializers.DecimalField(max_digits=10, decimal_places=2, read_only=True)
    item_count = serializers.IntegerField(read_only=True)

    class Meta:
        model = ShoppingCart
        fields = ["id", "items", "total", "item_count"]


class AddToCartSerializer(serializers.Serializer):
    """Accepts an asset_id to add to the user's cart."""

    asset_id = serializers.UUIDField()

    def validate_asset_id(self, value):
        from apps.assets.models import DigitalAsset
        try:
            asset = DigitalAsset.objects.get(id=value)
        except DigitalAsset.DoesNotExist:
            raise serializers.ValidationError("Invalid asset.")
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

        cart_items = cart.items.select_related("asset").all()
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
                    price_at_purchase=item.asset.price,
                    asset_title_snapshot=item.asset.title,
                )
                for item in cart_items
            ]
            OrderItem.objects.bulk_create(order_items)

            # Clear the cart after checkout
            cart_items.delete()

        return order
