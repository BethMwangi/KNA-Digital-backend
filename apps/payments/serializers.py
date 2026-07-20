from rest_framework import serializers

from .models import Payment


class PaymentSerializer(serializers.ModelSerializer):
    order_number = serializers.CharField(source="order.order_number", read_only=True)
    order_status = serializers.CharField(source="order.status", read_only=True)

    class Meta:
        model = Payment
        fields = [
            "id",
            "order",
            "order_number",
            "order_status",
            "provider",
            "status",
            "amount",
            "currency",
            "transaction_id",
            "paid_at",
            "created_at",
            "updated_at",
        ]
        read_only_fields = [
            "id",
            "status",
            "transaction_id",
            "paid_at",
            "created_at",
            "updated_at",
        ]


class InitiatePaymentSerializer(serializers.Serializer):
    """Start a payment for an order."""

    order_id = serializers.UUIDField()
    provider = serializers.ChoiceField(choices=Payment.Provider.choices)

    def validate_order_id(self, value):
        from apps.commerce.models import Order

        try:
            Order.objects.get(id=value, status=Order.Status.PENDING)
        except Order.DoesNotExist as err:
            raise serializers.ValidationError(
                "Order not found or is not in pending status."
            ) from err
        return value


class PaymentCallbackSerializer(serializers.Serializer):
    """Receives async callback data from a payment gateway."""

    transaction_id = serializers.CharField()
    status = serializers.ChoiceField(
        choices=["completed", "failed"],
    )
    provider_response = serializers.JSONField(required=False, default=dict)


class SimulatePaymentSerializer(serializers.Serializer):
    """
    Drives the MOCK gateway: stands in for the customer completing (or
    abandoning) checkout on a real provider's hosted payment page.
    Not valid for any other provider — those complete via /callback/
    once a real gateway integration is wired in.
    """

    outcome = serializers.ChoiceField(choices=["success", "failure"], default="success")
