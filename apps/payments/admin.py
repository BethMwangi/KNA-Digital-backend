from django.contrib import admin

from .models import Payment


@admin.register(Payment)
class PaymentAdmin(admin.ModelAdmin):
    list_display = [
        "id",
        "order",
        "provider",
        "status",
        "amount",
        "currency",
        "paid_at",
        "created_at",
    ]
    list_filter = ["status", "provider"]
    search_fields = ["transaction_id", "order__order_number"]
    readonly_fields = ["id", "transaction_id", "provider_response", "created_at", "updated_at"]
