"""
Commerce API views — Cart, Checkout, Orders, Licenses (SDD §16.8–§16.12).

All responses use the SDD §16.2 envelope.
"""

import logging

from django.db import transaction
from drf_spectacular.utils import extend_schema, extend_schema_view
from rest_framework import generics, permissions, status, viewsets
from rest_framework.response import Response

from apps.accounts.permissions import IsAccountActive

from .models import CartItem, License, Order, ShoppingCart
from .serializers import (
    AddToCartSerializer,
    CartDetailSerializer,
    CartSyncSerializer,
    CheckoutSerializer,
    LicenseSerializer,
    OrderSerializer,
)

logger = logging.getLogger(__name__)


def api_response(*, message: str, data=None, success: bool = True, status_code=status.HTTP_200_OK):
    """Standard response envelope (SDD §16.2)."""
    return Response(
        {"success": success, "message": message, "data": data or {}}, status=status_code
    )


# ------------------------------------------------------------------ #
# Public: Licenses
# ------------------------------------------------------------------ #
class LicenseViewSet(viewsets.ReadOnlyModelViewSet):
    queryset = License.objects.all()
    serializer_class = LicenseSerializer
    permission_classes = [permissions.AllowAny]

    def list(self, request, *args, **kwargs):
        response = super().list(request, *args, **kwargs)
        return api_response(message="Licenses retrieved.", data=response.data)

    def retrieve(self, request, *args, **kwargs):
        instance = self.get_object()
        serializer = self.get_serializer(instance)
        return api_response(message="License retrieved.", data=serializer.data)


# ------------------------------------------------------------------ #
# Cart — requires authentication
# ------------------------------------------------------------------ #
@extend_schema_view(
    get=extend_schema(
        summary="View cart",
        description="Retrieve the current user's shopping cart with all items, subtotals and total.",
        responses=CartDetailSerializer,
    ),
    post=extend_schema(
        summary="Add item to cart",
        description="Add a digital asset to the cart with a declared license (usage purpose).",
        request=AddToCartSerializer,
        responses=CartDetailSerializer,
    ),
)
class CartView(generics.GenericAPIView):
    """
    GET  → view cart
    POST → add item to cart
    """

    serializer_class = AddToCartSerializer

    permission_classes = [permissions.IsAuthenticated, IsAccountActive]

    def _get_or_create_cart(self, user):
        cart, _ = ShoppingCart.objects.get_or_create(user=user)
        return cart

    def get(self, request):
        cart = self._get_or_create_cart(request.user)
        serializer = CartDetailSerializer(cart)
        return api_response(message="Cart retrieved.", data=serializer.data)

    def post(self, request):
        serializer = AddToCartSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        cart = self._get_or_create_cart(request.user)
        asset_id = serializer.validated_data["asset_id"]
        license_id = serializer.validated_data["license_id"]

        # Prevent duplicates (same asset + same declared usage already in cart)
        if cart.items.filter(asset_id=asset_id, license_id=license_id).exists():
            logger.info(
                "CART ADD rejected (duplicate) user=%s asset=%s", request.user.email, asset_id
            )
            return api_response(
                success=False,
                message="This item is already in your cart.",
                status_code=status.HTTP_409_CONFLICT,
            )

        item = CartItem.objects.create(cart=cart, asset_id=asset_id, license_id=license_id)
        logger.info(
            "CART ADD user=%s asset=%s (%s) license=%s price=%s | cart now %d item(s), total=%s KES",
            request.user.email,
            item.asset.asset_number,
            item.asset.title[:40],
            item.license.name,
            item.asset.price,
            cart.item_count,
            cart.total,
        )
        cart_serializer = CartDetailSerializer(cart)
        return api_response(
            message="Item added to cart.",
            data=cart_serializer.data,
            status_code=status.HTTP_201_CREATED,
        )


@extend_schema(
    summary="Remove cart item",
    description="Remove a single item from the cart by its UUID.",
    responses=CartDetailSerializer,
)
class CartItemDeleteView(generics.DestroyAPIView):
    """DELETE /api/v1/cart/items/{id}/ — remove a single item."""

    serializer_class = CartDetailSerializer

    permission_classes = [permissions.IsAuthenticated, IsAccountActive]

    def get_queryset(self):
        return CartItem.objects.filter(cart__user=self.request.user)

    def destroy(self, request, *args, **kwargs):
        instance = self.get_object()
        asset_number, title = instance.asset.asset_number, instance.asset.title
        instance.delete(hard=True)  # cart items are truly deleted, not soft-deleted
        cart = ShoppingCart.objects.get(user=request.user)
        logger.info(
            "CART REMOVE user=%s asset=%s (%s) | cart now %d item(s), total=%s KES",
            request.user.email,
            asset_number,
            title[:40],
            cart.item_count,
            cart.total,
        )
        serializer = CartDetailSerializer(cart)
        return api_response(message="Item removed from cart.", data=serializer.data)


@extend_schema(
    summary="Clear cart",
    description="Remove all items from the cart.",
)
class CartClearView(generics.GenericAPIView):
    """POST /api/v1/cart/clear/ — empty the cart."""

    serializer_class = CartDetailSerializer

    permission_classes = [permissions.IsAuthenticated, IsAccountActive]

    def post(self, request):
        removed = 0
        try:
            cart = ShoppingCart.objects.get(user=request.user)
            # hard_delete: a soft-deleted row would still hold the
            # (cart, asset, license) unique slot and block re-adding.
            removed = cart.items.all().hard_delete()[0]
        except ShoppingCart.DoesNotExist:
            pass
        logger.info("CART CLEAR user=%s removed=%d items", request.user.email, removed)
        return api_response(message="Cart cleared.")


@extend_schema(
    summary="Sync cart",
    description="Completely replace the user's cart with the provided items array.",
    request=CartSyncSerializer,
    responses=CartDetailSerializer,
)
class CartSyncView(generics.GenericAPIView):
    """POST /api/v1/cart/sync/ — bulk update cart."""

    serializer_class = CartSyncSerializer
    permission_classes = [permissions.IsAuthenticated, IsAccountActive]

    def post(self, request):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        cart, _ = ShoppingCart.objects.get_or_create(user=request.user)

        with transaction.atomic():
            cart.items.all().delete()
            new_items = [
                CartItem(cart=cart, asset_id=item["asset_id"], license_id=item["license_id"])
                for item in serializer.validated_data["items"]
            ]
            CartItem.objects.bulk_create(new_items)

        cart_serializer = CartDetailSerializer(cart)
        return api_response(message="Cart synchronized.", data=cart_serializer.data)


# ------------------------------------------------------------------ #
# Checkout → create Order from Cart
# ------------------------------------------------------------------ #
class CheckoutView(generics.CreateAPIView):
    """POST /api/v1/orders/checkout/ — place an order from cart contents."""

    serializer_class = CheckoutSerializer
    permission_classes = [permissions.IsAuthenticated, IsAccountActive]

    def create(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        order = serializer.save()
        return api_response(
            message="Order placed successfully.",
            data=OrderSerializer(order).data,
            status_code=status.HTTP_201_CREATED,
        )


# ------------------------------------------------------------------ #
# Orders — customers see their own, admins see all
# ------------------------------------------------------------------ #
class OrderViewSet(viewsets.ReadOnlyModelViewSet):
    serializer_class = OrderSerializer
    permission_classes = [permissions.IsAuthenticated, IsAccountActive]

    def get_queryset(self):
        user = self.request.user
        # Guard for drf-spectacular anonymous schema introspection
        if not user or not user.is_authenticated:
            return Order.objects.none()
        # items__asset__variants: nested OrderItemSerializer resolves each
        # asset's thumbnail via public_variant_url(), which iterates
        # asset.variants.all() — prefetch or every order item N+1s it.
        base = Order.objects.prefetch_related("items__asset__variants", "items__license")
        if user.is_admin or user.is_super_admin:
            return base.select_related("user")
        return base.filter(user=user)

    def list(self, request, *args, **kwargs):
        response = super().list(request, *args, **kwargs)
        return api_response(message="Orders retrieved.", data=response.data)

    def retrieve(self, request, *args, **kwargs):
        instance = self.get_object()
        serializer = self.get_serializer(instance)
        return api_response(message="Order retrieved.", data=serializer.data)
