"""Django admin for user & audit log management (internal ops)."""
from django.contrib import admin
from django.contrib.auth.admin import UserAdmin as DjangoUserAdmin

from .models import AuditLog, User


@admin.register(User)
class UserAdmin(DjangoUserAdmin):
    ordering = ["-created_at"]
    list_display = ["email", "full_name", "role", "account_status", "email_verified", "last_login"]
    list_filter = ["role", "account_status", "email_verified"]
    search_fields = ["email", "first_name", "last_name"]
    readonly_fields = ["last_login", "created_at", "updated_at"]
    fieldsets = (
        (None, {"fields": ("email", "password")}),
        ("Profile", {"fields": ("first_name", "last_name", "phone_number")}),
        ("Access", {"fields": ("role", "account_status", "email_verified", "is_staff", "is_superuser", "is_active")}),
        ("Dates", {"fields": ("last_login", "created_at", "updated_at")}),
    )
    add_fieldsets = (
        (None, {
            "classes": ("wide",),
            "fields": ("email", "first_name", "last_name", "role", "password1", "password2"),
        }),
    )


@admin.register(AuditLog)
class AuditLogAdmin(admin.ModelAdmin):
    """Immutable — read-only in admin (SDD §20.3)."""
    list_display = ["created_at", "action", "user", "ip_address", "success"]
    list_filter = ["action", "success"]
    search_fields = ["user__email", "ip_address"]

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False
