"""Payments URL routes."""

from django.urls import path

from . import views

urlpatterns = [
    # Static paths must precede the <uuid:pk> pattern below, or it swallows them.
    path("payments/", views.PaymentListView.as_view(), name="payment-list"),
    path("payments/initiate/", views.PaymentInitiateView.as_view(), name="payment-initiate"),
    path("payments/callback/", views.PaymentCallbackView.as_view(), name="payment-callback"),
    path("payments/<uuid:pk>/", views.PaymentDetailView.as_view(), name="payment-detail"),
    path(
        "payments/<uuid:pk>/simulate/", views.PaymentSimulateView.as_view(), name="payment-simulate"
    ),
]
