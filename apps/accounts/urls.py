"""Routes for /api/v1/auth, /api/v1/users and /api/v1/admin/users (SDD §16)."""

from django.urls import include, path
from rest_framework.routers import DefaultRouter

from . import views

router = DefaultRouter()
router.register("admin/users", views.AdminUserViewSet, basename="admin-users")

auth_patterns = [
    path("register", views.RegisterView.as_view(), name="auth-register"),
    path("login", views.LoginView.as_view(), name="auth-login"),
    path("refresh", views.RefreshView.as_view(), name="auth-refresh"),
    path("logout", views.LogoutView.as_view(), name="auth-logout"),
    path("forgot-password", views.PasswordResetRequestView.as_view(), name="auth-forgot-password"),
    path("reset-password", views.PasswordResetConfirmView.as_view(), name="auth-reset-password"),
    path("verify-email", views.EmailVerifyView.as_view(), name="auth-verify-email"),
]

user_patterns = [
    path("me", views.MeView.as_view(), name="users-me"),
    path("password", views.ChangePasswordView.as_view(), name="users-password"),
]

urlpatterns = [
    path("auth/", include(auth_patterns)),
    path("users/", include(user_patterns)),
    path("", include(router.urls)),
]
