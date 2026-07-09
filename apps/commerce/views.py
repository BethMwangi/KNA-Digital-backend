"""
Commerce API views — Cart, Checkout, Orders, Licenses (SDD §16.8–§16.12).

All responses use the SDD §16.2 envelope.
"""
from rest_framework import generics, mixins, permissions, status, viewsets
from rest_framework.decorators import action
from rest_framework.response import Response

from apps.accounts.permissions import IsAccountActive, IsContentEditorOrAbove

from .models import AssetPrice, CartItem, License, Order, ShoppingCart
from .serializers import (
    AddToCartSerializer,
    AssetPriceSerializer,
    CartDetailSerializer,
    CheckoutSerializer,
    LicenseSerializer,
    OrderSerializer,
)


def api_response(*, message: str, data=None, success: bool = True, status_code=status.HTTP_200_OK):
    """Standard response envelope (SDD §16.2)."""
    return Response({"success": success, "message": message, "data": data or {}}, status=status_code)


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
# Public: Asset Prices (by asset)
# ------------------------------------------------------------------ #
class AssetPriceViewSet(viewsets.ReadOnlyModelViewSet):
    serializer_class = AssetPriceSerializer
    permission_classes = [permissions.AllowAny]

    def get_queryset(self):
        queryset = AssetPrice.objects.filter(is_active=True).select_related("asset", "license")
        asset_id = self.request.query_params.get("asset")
        if asset_id:
            queryset = queryset.filter(asset_id=asset_id)
        return queryset

    def list(self, request, *args, **kwargs):
        response = super().list(request, *args, **kwargs)
        return api_response(message="Prices retrieved.", data=response.data)


# ------------------------------------------------------------------ #
# Cart — requires authentication
# ------------------------------------------------------------------ #
class CartView(generics.GenericAPIView):
    """
    GET  → view cart
    POST → add item to cart
    """

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
        asset_price_id = serializer.validated_data["asset_price_id"]

        # Prevent duplicates
        if cart.items.filter(asset_price_id=asset_price_id).exists():
            return api_response(
                success=False,
                message="This item is already in your cart.",
                status_code=status.HTTP_409_CONFLICT,
            )

        CartItem.objects.create(cart=cart, asset_price_id=asset_price_id)
        cart_serializer = CartDetailSerializer(cart)
        return api_response(
            message="Item added to cart.",
            data=cart_serializer.data,
            status_code=status.HTTP_201_CREATED,
        )


class CartItemDeleteView(generics.DestroyAPIView):
    """DELETE /api/v1/cart/items/{id}/ — remove a single item."""

    permission_classes = [permissions.IsAuthenticated, IsAccountActive]

    def get_queryset(self):
        return CartItem.objects.filter(cart__user=self.request.user)

    def destroy(self, request, *args, **kwargs):
        instance = self.get_object()
        instance.delete(hard=True)  # cart items are truly deleted, not soft-deleted
        cart = ShoppingCart.objects.get(user=request.user)
        serializer = CartDetailSerializer(cart)
        return api_response(message="Item removed from cart.", data=serializer.data)


class CartClearView(generics.GenericAPIView):
    """POST /api/v1/cart/clear/ — empty the cart."""

    permission_classes = [permissions.IsAuthenticated, IsAccountActive]

    def post(self, request):
        try:
            cart = ShoppingCart.objects.get(user=request.user)
            cart.items.all().delete()
        except ShoppingCart.DoesNotExist:
            pass
        return api_response(message="Cart cleared.")


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
        if user.is_admin or user.is_super_admin:
            return Order.objects.all().select_related("user")
        return Order.objects.filter(user=user)

    def list(self, request, *args, **kwargs):
        response = super().list(request, *args, **kwargs)
        return api_response(message="Orders retrieved.", data=response.data)

    def retrieve(self, request, *args, **kwargs):
        instance = self.get_object()
        serializer = self.get_serializer(instance)
        return api_response(message="Order retrieved.", data=serializer.data)
