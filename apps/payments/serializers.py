from rest_framework import serializers

from .models import Payment


class PaymentSerializer(serializers.ModelSerializer):
    class Meta:
        model = Payment
        fields = [
            "id",
            "order",
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
            order = Order.objects.get(id=value, status=Order.Status.PENDING)
        except Order.DoesNotExist:
            raise serializers.ValidationError(
                "Order not found or is not in pending status."
            )
        return value


class PaymentCallbackSerializer(serializers.Serializer):
    """Receives async callback data from a payment gateway."""

    transaction_id = serializers.CharField()
    status = serializers.ChoiceField(
        choices=["completed", "failed"],
    )
    provider_response = serializers.JSONField(required=False, default=dict)
