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
            "checkout_url",
            "paid_at",
            "created_at",
            "updated_at",
        ]
        read_only_fields = [
            "id",
            "status",
            "transaction_id",
            "checkout_url",
            "paid_at",
            "created_at",
            "updated_at",
        ]


class BillingDetailsSerializer(serializers.Serializer):
    """Billing info forwarded to the payment gateway."""

    first_name = serializers.CharField(max_length=100)
    last_name = serializers.CharField(max_length=100)
    email = serializers.EmailField()
    phone = serializers.CharField(max_length=30)


class InitiatePaymentSerializer(serializers.Serializer):
    """Start a payment for an order."""

    order_id = serializers.UUIDField()
    provider = serializers.ChoiceField(choices=Payment.Provider.choices)
    billing = BillingDetailsSerializer(required=False)

    def validate_order_id(self, value):
        from apps.commerce.models import Order

        try:
            Order.objects.get(id=value, status=Order.Status.PENDING)
        except Order.DoesNotExist as err:
            raise serializers.ValidationError(
                "Order not found or is not in pending status."
            ) from err
        return value

    def validate(self, attrs):
        # Pesaflow requires billing details — enforce at serializer level.
        if attrs["provider"] == Payment.Provider.PESAFLOW and not attrs.get("billing"):
            raise serializers.ValidationError(
                {"billing": "Billing details are required for Pesaflow payments."}
            )
        return attrs


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
