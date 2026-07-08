"""
Accounts models.

Implements the SDD:
-  `users` table (uuid pk, names, unique email, phone, account_status,
  email_verified, last_login, audit timestamps)
-  user roles: Guest (unauthenticated), Customer, Content Editor,
  Administrator, Super Administrator.

Design decision (senior note): Phase One uses a single `role` field with a
TextChoices enum instead of the full roles/permissions/role_permissions
many-to-many tables. The permission matrix in SDD §17.5 is static for Phase
One, so RBAC is enforced in code (see permissions.py). If Phase Two (MMS)
needs dynamic, admin-editable permissions, this can be migrated to Django's
Group/Permission tables without touching the API surface.
"""
from django.contrib.auth.models import AbstractBaseUser, PermissionsMixin
from django.core.validators import RegexValidator
from django.db import models
from django.utils import timezone
from django.utils.translation import gettext_lazy as _

from core.models import BaseModel

from .managers import UserManager


class Role(models.TextChoices):
    """Guest is simply an unauthenticated request."""

    CUSTOMER = "customer", _("Customer")
    CONTENT_EDITOR = "content_editor", _("Content Editor")
    ADMIN = "admin", _("Administrator")
    SUPER_ADMIN = "super_admin", _("Super Administrator")


class AccountStatus(models.TextChoices):
    ACTIVE = "active", _("Active")
    SUSPENDED = "suspended", _("Suspended")


class User(BaseModel, AbstractBaseUser, PermissionsMixin):
    """Platform user (customers and staff)."""

    first_name = models.CharField(_("first name"), max_length=100)
    last_name = models.CharField(_("last name"), max_length=100)
    email = models.EmailField(_("email address"), max_length=255, unique=True, db_index=True)
    phone_number = models.CharField(
        _("phone number"),
        max_length=20,
        blank=True,
        validators=[
            RegexValidator(
                regex=r"^\+?[0-9]{7,15}$",
                message=_("Enter a valid phone number, e.g. +254712345678."),
            )
        ],
    )
    role = models.CharField(
        _("role"), max_length=32, choices=Role.choices, default=Role.CUSTOMER, db_index=True
    )
    account_status = models.CharField(
        _("account status"),
        max_length=20,
        choices=AccountStatus.choices,
        default=AccountStatus.ACTIVE,
        db_index=True,
    )
    email_verified = models.BooleanField(_("email verified"), default=False)
    is_staff = models.BooleanField(
        _("staff status"),
        default=False,
        help_text=_("Allows access to the Django admin site."),
    )
    is_active = models.BooleanField(_("active"), default=True)

    # last_login is provided by AbstractBaseUser .

    objects = UserManager()

    USERNAME_FIELD = "email"
    REQUIRED_FIELDS = ["first_name", "last_name"]

    class Meta:
        db_table = "users"
        verbose_name = _("user")
        verbose_name_plural = _("users")
        indexes = [
            models.Index(fields=["email"]),
            models.Index(fields=["account_status"]),
        ]

    def __str__(self) -> str:
        return self.email

    # ------------------------------------------------------------------ #
    # Convenience role checks used by DRF permission classes
    # ------------------------------------------------------------------ #
    @property
    def full_name(self) -> str:
        return f"{self.first_name} {self.last_name}".strip()

    @property
    def is_customer(self) -> bool:
        return self.role == Role.CUSTOMER

    @property
    def is_content_editor(self) -> bool:
        return self.role == Role.CONTENT_EDITOR

    @property
    def is_admin(self) -> bool:
        return self.role in {Role.ADMIN, Role.SUPER_ADMIN}

    @property
    def is_super_admin(self) -> bool:
        return self.role == Role.SUPER_ADMIN

    @property
    def is_suspended(self) -> bool:
        return self.account_status == AccountStatus.SUSPENDED

    def mark_email_verified(self):
        if not self.email_verified:
            self.email_verified = True
            self.save(update_fields=["email_verified", "updated_at"])


class AuditLog(BaseModel):
    """
    immutable audit trail for security-relevant events.
    Rows are insert-only; no update/delete API is exposed.
    """

    class Action(models.TextChoices):
        LOGIN = "login", _("Login")
        LOGOUT = "logout", _("Logout")
        REGISTER = "register", _("Registration")
        PASSWORD_CHANGE = "password_change", _("Password Change")
        PASSWORD_RESET_REQUEST = "password_reset_request", _("Password Reset Requested")
        PASSWORD_RESET = "password_reset", _("Password Reset")
        EMAIL_VERIFIED = "email_verified", _("Email Verified")
        ROLE_CHANGE = "role_change", _("Role Change")
        USER_CREATED = "user_created", _("User Created")

    user = models.ForeignKey(
        User, null=True, blank=True, on_delete=models.SET_NULL, related_name="audit_logs"
    )
    action = models.CharField(max_length=64, choices=Action.choices, db_index=True)
    resource = models.CharField(max_length=255, blank=True)
    ip_address = models.GenericIPAddressField(null=True, blank=True)
    user_agent = models.TextField(blank=True)
    success = models.BooleanField(default=True)
    metadata = models.JSONField(default=dict, blank=True)

    class Meta:
        db_table = "audit_logs"
        ordering = ["-created_at"]

    def __str__(self) -> str:
        return f"{self.action} by {self.user_id} at {self.created_at:%Y-%m-%d %H:%M}"


def log_event(*, user=None, action: str, request=None, success: bool = True, **metadata):
    """Small helper so views can audit in one line."""
    ip, agent = None, ""
    if request is not None:
        xff = request.META.get("HTTP_X_FORWARDED_FOR")
        ip = xff.split(",")[0].strip() if xff else request.META.get("REMOTE_ADDR")
        agent = request.META.get("HTTP_USER_AGENT", "")[:1000]
    return AuditLog.objects.create(
        user=user if getattr(user, "is_authenticated", False) else None,
        action=action,
        ip_address=ip,
        user_agent=agent,
        success=success,
        metadata=metadata,
    )
