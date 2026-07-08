"""
Role-Based Access Control.

Usage in any app (assets, orders, ...):

    class AssetAdminViewSet(viewsets.ModelViewSet):
        permission_classes = [IsAuthenticated, IsContentEditorOrAbove]
"""
from rest_framework.permissions import BasePermission

from .models import Role


class IsAccountActive(BasePermission):
    """Suspended accounts can authenticate a token but access nothing."""

    message = "Your account has been suspended. Contact support."

    def has_permission(self, request, view):
        user = request.user
        return bool(user and user.is_authenticated and not user.is_suspended)


class RolePermission(BasePermission):
    """Base class — subclasses declare the allowed roles."""

    allowed_roles: set = set()

    def has_permission(self, request, view):
        user = request.user
        return bool(
            user
            and user.is_authenticated
            and not user.is_suspended
            and user.role in self.allowed_roles
        )


class IsCustomer(RolePermission):
    allowed_roles = {Role.CUSTOMER, Role.CONTENT_EDITOR, Role.ADMIN, Role.SUPER_ADMIN}


class IsContentEditorOrAbove(RolePermission):
    """Upload/edit assets, manage categories & collections (SDD §17.4)."""

    allowed_roles = {Role.CONTENT_EDITOR, Role.ADMIN, Role.SUPER_ADMIN}


class IsAdminOrAbove(RolePermission):
    """Manage users, delete assets, view reports (SDD §17.4)."""

    allowed_roles = {Role.ADMIN, Role.SUPER_ADMIN}


class IsSuperAdmin(RolePermission):
    """System settings, permissions, audit logs (SDD §17.4)."""

    allowed_roles = {Role.SUPER_ADMIN}


class IsSelfOrAdmin(BasePermission):
    """Object-level: users manage their own profile; admins manage anyone."""

    def has_object_permission(self, request, view, obj):
        return obj == request.user or request.user.is_admin
