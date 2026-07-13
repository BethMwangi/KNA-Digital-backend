"""
Payments API views (SDD §16.13).

Gateway integration is stubbed — plug in real adapters when ready.
"""

import uuid

from django.utils import timezone
from rest_framework import generics, permissions, status
from rest_framework.response import Response

from apps.accounts.permissions import IsAccountActive
from apps.commerce.models import Order

from .models import Payment
from .serializers import (
    InitiatePaymentSerializer,
    PaymentCallbackSerializer,
    PaymentSerializer,
)


def api_response(*, message: str, data=None, success: bool = True, status_code=status.HTTP_200_OK):
    """Standard response envelope (SDD §16.2)."""
    return Response(
        {"success": success, "message": message, "data": data or {}}, status=status_code
    )


class PaymentInitiateView(generics.CreateAPIView):
    """POST /api/v1/payments/initiate/ — start a payment for an order."""

    serializer_class = InitiatePaymentSerializer
    permission_classes = [permissions.IsAuthenticated, IsAccountActive]

    def create(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        order = Order.objects.get(id=serializer.validated_data["order_id"])

        # Ensure the order belongs to the requesting user
        if order.user != request.user:
            return api_response(
                success=False,
                message="You do not have permission to pay for this order.",
                status_code=status.HTTP_403_FORBIDDEN,
            )

        payment = Payment.objects.create(
            order=order,
            provider=serializer.validated_data["provider"],
            amount=order.total,
            currency=order.currency,
            status=Payment.Status.INITIATED,
            transaction_id=f"TXN-{uuid.uuid4().hex[:12].upper()}",
        )

        # TODO: Call the actual gateway adapter here based on payment.provider
        # For now, we just return the payment record so frontend can redirect

        return api_response(
            message="Payment initiated.",
            data=PaymentSerializer(payment).data,
            status_code=status.HTTP_201_CREATED,
        )


class PaymentCallbackView(generics.GenericAPIView):
    """
    POST /api/v1/payments/callback/ — webhook from payment gateway.

    In production this should verify signatures from the provider.
    """

    serializer_class = PaymentCallbackSerializer
    permission_classes = [permissions.AllowAny]  # Gateways call this unauthenticated

    def post(self, request):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        txn_id = serializer.validated_data["transaction_id"]
        new_status = serializer.validated_data["status"]

        try:
            payment = Payment.objects.get(transaction_id=txn_id)
        except Payment.DoesNotExist:
            return api_response(
                success=False,
                message="Transaction not found.",
                status_code=status.HTTP_404_NOT_FOUND,
            )

        if new_status == "completed":
            payment.status = Payment.Status.COMPLETED
            payment.paid_at = timezone.now()
            payment.order.status = Order.Status.PAID
            payment.order.save(update_fields=["status", "updated_at"])
        else:
            payment.status = Payment.Status.FAILED
            payment.order.status = Order.Status.FAILED
            payment.order.save(update_fields=["status", "updated_at"])

        payment.provider_response = serializer.validated_data.get("provider_response", {})
        payment.save(update_fields=["status", "paid_at", "provider_response", "updated_at"])

        return api_response(message=f"Payment {payment.status}.")


class PaymentDetailView(generics.RetrieveAPIView):
    """GET /api/v1/payments/{id}/ — check payment status."""

    serializer_class = PaymentSerializer
    permission_classes = [permissions.IsAuthenticated, IsAccountActive]

    def get_queryset(self):
        user = self.request.user
        if user.is_admin or user.is_super_admin:
            return Payment.objects.all()
        return Payment.objects.filter(order__user=user)

    def retrieve(self, request, *args, **kwargs):
        instance = self.get_object()
        serializer = self.get_serializer(instance)
        return api_response(message="Payment retrieved.", data=serializer.data)
