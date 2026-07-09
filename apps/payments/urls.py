"""Payments URL routes."""
from django.urls import path

from . import views

urlpatterns = [
    path("payments/initiate/", views.PaymentInitiateView.as_view(), name="payment-initiate"),
    path("payments/callback/", views.PaymentCallbackView.as_view(), name="payment-callback"),
    path("payments/<uuid:pk>/", views.PaymentDetailView.as_view(), name="payment-detail"),
]
