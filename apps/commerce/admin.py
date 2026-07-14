from django.contrib import admin

from .models import CartItem, License, Order, OrderItem, ShoppingCart


@admin.register(License)
class LicenseAdmin(admin.ModelAdmin):
    list_display = ["name", "slug", "allows_commercial", "allows_modification"]
    prepopulated_fields = {"slug": ("name",)}


class OrderItemInline(admin.TabularInline):
    model = OrderItem
    extra = 0
    readonly_fields = ["asset", "license", "price_at_purchase", "asset_title_snapshot"]


@admin.register(Order)
class OrderAdmin(admin.ModelAdmin):
    list_display = ["order_number", "user", "status", "total", "currency", "created_at"]
    list_filter = ["status", "currency"]
    search_fields = ["order_number", "user__email"]
    readonly_fields = ["id", "order_number", "subtotal", "tax", "total", "created_at"]
    inlines = [OrderItemInline]


class CartItemInline(admin.TabularInline):
    model = CartItem
    extra = 0
    readonly_fields = ["asset", "license"]


@admin.register(ShoppingCart)
class ShoppingCartAdmin(admin.ModelAdmin):
    list_display = ["user", "item_count", "total"]
    readonly_fields = ["user"]
    inlines = [CartItemInline]
