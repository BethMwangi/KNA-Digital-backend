"""
Payments API views (SDD §16.13).

Real gateway integration (M-Pesa, eCitizen, cards) is stubbed for later —
see gateways.py note in models.py. Until then, provider="mock" gives a
full working simulation: initiate -> simulate -> order paid -> downloads
granted -> confirmation email, so the whole storefront can be built and
tested end-to-end before a real gateway is plugged in.
"""

import logging
import uuid

from rest_framework import generics, permissions, status
from rest_framework.response import Response

from apps.accounts.permissions import IsAccountActive
from apps.commerce.models import Order

from .models import Payment
from .serializers import (
    InitiatePaymentSerializer,
    PaymentCallbackSerializer,
    PaymentSerializer,
    SimulatePaymentSerializer,
)
from .services import complete_payment, fail_payment

logger = logging.getLogger(__name__)


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
            logger.warning(
                "PAYMENT INITIATE rejected: user=%s tried to pay order=%s owned by %s",
                request.user.email,
                order.order_number,
                order.user.email,
            )
            return api_response(
                success=False,
                message="You do not have permission to pay for this order.",
                status_code=status.HTTP_403_FORBIDDEN,
            )

        provider = serializer.validated_data["provider"]
        payment = Payment.objects.create(
            order=order,
            provider=provider,
            amount=order.total,
            currency=order.currency,
            status=Payment.Status.INITIATED,
            transaction_id=f"TXN-{uuid.uuid4().hex[:12].upper()}",
        )

        logger.info(
            "PAYMENT INITIATE user=%s order=%s provider=%s amount=%s %s txn=%s payment=%s",
            request.user.email,
            order.order_number,
            provider,
            payment.amount,
            payment.currency,
            payment.transaction_id,
            payment.id,
        )

        data = PaymentSerializer(payment).data
        if provider == Payment.Provider.MOCK:
            # No real gateway to redirect to — the frontend calls this
            # next to stand in for "customer completes the hosted
            # payment page and the gateway calls us back".
            data["simulate_url"] = f"/api/v1/payments/{payment.id}/simulate/"
        # TODO: for real providers, call the gateway adapter here and
        # return whatever redirect/STK-push info it gives (see gateways.py).

        return api_response(
            message="Payment initiated.",
            data=data,
            status_code=status.HTTP_201_CREATED,
        )


class PaymentSimulateView(generics.GenericAPIView):
    """
    POST /api/v1/payments/{id}/simulate/ — MOCK gateway only.

    Stands in for the customer finishing checkout on the provider's
    hosted page and the provider calling our webhook: body
    {"outcome": "success"} (default) or {"outcome": "failure"}.
    """

    serializer_class = SimulatePaymentSerializer
    permission_classes = [permissions.IsAuthenticated, IsAccountActive]

    def get_queryset(self):
        return Payment.objects.select_related("order", "order__user")

    def post(self, request, pk):
        try:
            payment = self.get_queryset().get(id=pk)
        except Payment.DoesNotExist:
            return api_response(
                success=False,
                message="Payment not found.",
                status_code=status.HTTP_404_NOT_FOUND,
            )

        if payment.order.user != request.user:
            return api_response(
                success=False,
                message="You do not have permission to act on this payment.",
                status_code=status.HTTP_403_FORBIDDEN,
            )
        if payment.provider != Payment.Provider.MOCK:
            return api_response(
                success=False,
                message=f"Only mock payments can be simulated; this is '{payment.provider}'. "
                "Real providers complete via their own callback.",
                status_code=status.HTTP_400_BAD_REQUEST,
            )
        if payment.status not in (Payment.Status.INITIATED, Payment.Status.PENDING):
            return api_response(
                success=False,
                message=f"This payment is already '{payment.status}' and can't be simulated again.",
                status_code=status.HTTP_409_CONFLICT,
            )

        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        outcome = serializer.validated_data["outcome"]

        logger.info(
            "PAYMENT SIMULATE user=%s payment=%s order=%s outcome=%s",
            request.user.email,
            payment.id,
            payment.order.order_number,
            outcome,
        )

        fake_response = {
            "simulated": True,
            "outcome": outcome,
            "gateway_ref": f"MOCK-{uuid.uuid4().hex[:10].upper()}",
        }
        if outcome == "success":
            payment = complete_payment(payment, provider_response=fake_response)
            message = "Payment successful."
        else:
            payment = fail_payment(payment, provider_response=fake_response)
            message = "Payment failed (simulated). Your order is still pending — try again."

        payment.refresh_from_db()
        return api_response(message=message, data=PaymentSerializer(payment).data)


class PaymentCallbackView(generics.GenericAPIView):
    """
    POST /api/v1/payments/callback/ — webhook from a real payment gateway.

    In production this should verify signatures from the provider before
    trusting the body. Kept separate from /simulate/ so the mock path
    (auth'd, scoped to the caller) and the real webhook path (unauth'd,
    scoped by transaction_id, provider-signed) never share validation.
    """

    serializer_class = PaymentCallbackSerializer
    permission_classes = [permissions.AllowAny]  # Gateways call this unauthenticated

    def post(self, request):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        txn_id = serializer.validated_data["transaction_id"]
        new_status = serializer.validated_data["status"]
        provider_response = serializer.validated_data.get("provider_response", {})

        try:
            payment = Payment.objects.select_related("order", "order__user").get(
                transaction_id=txn_id
            )
        except Payment.DoesNotExist:
            logger.warning("PAYMENT CALLBACK unknown transaction_id=%s", txn_id)
            return api_response(
                success=False,
                message="Transaction not found.",
                status_code=status.HTTP_404_NOT_FOUND,
            )

        logger.info(
            "PAYMENT CALLBACK payment=%s order=%s provider=%s status=%s",
            payment.id,
            payment.order.order_number,
            payment.provider,
            new_status,
        )
        if new_status == "completed":
            payment = complete_payment(payment, provider_response=provider_response)
        else:
            payment = fail_payment(payment, provider_response=provider_response)

        return api_response(message=f"Payment {payment.status}.")


class PaymentListView(generics.ListAPIView):
    """GET /api/v1/payments/?order=<id> — my payment attempts, optionally
    scoped to one order (useful for a retry UI after a failed attempt)."""

    serializer_class = PaymentSerializer
    permission_classes = [permissions.IsAuthenticated, IsAccountActive]

    def get_queryset(self):
        user = self.request.user
        if not user or not user.is_authenticated:
            return Payment.objects.none()
        qs = Payment.objects.filter(order__user=user).select_related("order")
        order_id = self.request.query_params.get("order")
        if order_id:
            qs = qs.filter(order_id=order_id)
        return qs

    def list(self, request, *args, **kwargs):
        response = super().list(request, *args, **kwargs)
        return api_response(message="Payments retrieved.", data=response.data)


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
