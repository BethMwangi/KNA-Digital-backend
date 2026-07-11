"""Commerce URL routes — /api/v1/licenses, /api/v1/prices, /api/v1/cart, /api/v1/orders."""
from django.urls import include, path
from rest_framework.routers import DefaultRouter

from . import views

router = DefaultRouter()
router.register(r"licenses", views.LicenseViewSet, basename="license")
router.register(r"prices", views.AssetPriceViewSet, basename="asset-price")
router.register(r"orders", views.OrderViewSet, basename="order")

cart_patterns = [
    path("", views.CartView.as_view(), name="cart"),
    path("items/<uuid:pk>/", views.CartItemDeleteView.as_view(), name="cart-item-delete"),
    path("clear/", views.CartClearView.as_view(), name="cart-clear"),
]

urlpatterns = [
    path("", include(router.urls)),
    path("cart/", include(cart_patterns)),
    path("orders/checkout/", views.CheckoutView.as_view(), name="checkout"),
]
