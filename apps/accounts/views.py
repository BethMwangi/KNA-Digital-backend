"""
Accounts API — class-based views mapping to SDD §16.5 (Auth APIs),
§16.6 (User APIs) and §16.15 (Admin user management).

All responses follow the SDD §16.2 envelope:
    {"success": true, "message": "...", "data": {...}}
via the api_response helper below (core.exceptions handles errors).
"""

from django.utils import timezone
from drf_spectacular.utils import extend_schema, inline_serializer
from rest_framework import generics, serializers, status, viewsets
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.response import Response
from rest_framework.throttling import AnonRateThrottle
from rest_framework.views import APIView
from rest_framework_simplejwt.exceptions import TokenError
from rest_framework_simplejwt.tokens import RefreshToken
from rest_framework_simplejwt.views import (
    TokenObtainPairView,
    TokenRefreshView,
)

from .models import AuditLog, User, log_event
from .permissions import IsAccountActive, IsAdminOrAbove, IsSuperAdmin
from .serializers import (
    AdminUserSerializer,
    ChangePasswordSerializer,
    EmailVerifySerializer,
    LoginSerializer,
    PasswordResetConfirmSerializer,
    PasswordResetRequestSerializer,
    RegisterSerializer,
    ResendVerificationSerializer,
    UserSerializer,
)
from .tasks import send_password_reset_email_task, send_verification_email_task


def api_response(
    *,
    message: str,
    data=None,
    success: bool = True,
    status_code=status.HTTP_200_OK,
):
    """Standard response envelope (SDD §16.2)."""
    return Response(
        {
            "success": success,
            "message": message,
            "data": data or {},
        },
        status=status_code,
    )


class AuthThrottle(AnonRateThrottle):
    """Tighter limit on credential endpoints (SDD §16.20 rate limiting)."""

    rate = "10/min"


# --------------------------------------------------------------------- #
# POST /api/v1/auth/register
# --------------------------------------------------------------------- #
class RegisterView(generics.CreateAPIView):
    serializer_class = RegisterSerializer
    permission_classes = [AllowAny]
    throttle_classes = [AuthThrottle]

    def create(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        user = serializer.save()
        send_verification_email_task.delay(str(user.id))
        log_event(
            user=user,
            action=AuditLog.Action.REGISTER,
            request=request,
        )
        return api_response(
            message=("Account created. Please check your email to " "verify your address."),
            data=UserSerializer(user).data,
            status_code=status.HTTP_201_CREATED,
        )


# --------------------------------------------------------------------- #
# POST /api/v1/auth/login  — returns access + refresh + profile
# --------------------------------------------------------------------- #
class LoginView(TokenObtainPairView):
    serializer_class = LoginSerializer
    throttle_classes = [AuthThrottle]

    def post(self, request, *args, **kwargs):
        response = super().post(request, *args, **kwargs)
        if response.status_code == status.HTTP_200_OK:
            email = request.data.get("email", "")
            user = User.objects.filter(email__iexact=email).first()
            if user:
                user.last_login = timezone.now()
                user.save(update_fields=["last_login"])
                log_event(
                    user=user,
                    action=AuditLog.Action.LOGIN,
                    request=request,
                )
            return api_response(
                message="Login successful.",
                data=response.data,
            )
        return response


# --------------------------------------------------------------------- #
# POST /api/v1/auth/refresh
# --------------------------------------------------------------------- #
class RefreshView(TokenRefreshView):
    def post(self, request, *args, **kwargs):
        response = super().post(request, *args, **kwargs)
        if response.status_code == status.HTTP_200_OK:
            return api_response(message="Token refreshed.", data=response.data)
        return response


# --------------------------------------------------------------------- #
# POST /api/v1/auth/logout — blacklists the refresh token
# --------------------------------------------------------------------- #
class LogoutView(APIView):
    permission_classes = [IsAuthenticated]

    @extend_schema(
        summary="Log out",
        description="Blacklists the given refresh token, ending the session.",
        request=inline_serializer(
            name="LogoutRequest", fields={"refresh": serializers.CharField()}
        ),
    )
    def post(self, request):
        refresh = request.data.get("refresh")
        if not refresh:
            return api_response(
                success=False,
                message="A refresh token is required to log out.",
                status_code=status.HTTP_400_BAD_REQUEST,
            )
        try:
            RefreshToken(refresh).blacklist()
        except TokenError:
            return api_response(
                success=False,
                message="Invalid or already blacklisted token.",
                status_code=status.HTTP_400_BAD_REQUEST,
            )
        log_event(
            user=request.user,
            action=AuditLog.Action.LOGOUT,
            request=request,
        )
        return api_response(message="Logged out successfully.")


# --------------------------------------------------------------------- #
# POST /api/v1/auth/forgot-password
# --------------------------------------------------------------------- #
class PasswordResetRequestView(APIView):
    permission_classes = [AllowAny]
    throttle_classes = [AuthThrottle]

    @extend_schema(
        summary="Request a password reset",
        description="Sends a reset link if the email is registered. Always returns the "
        "same message either way, to avoid revealing whether an account exists.",
        request=PasswordResetRequestSerializer,
    )
    def post(self, request):
        serializer = PasswordResetRequestSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        user = User.objects.filter(email__iexact=serializer.validated_data["email"]).first()
        if user and not user.is_suspended:
            send_password_reset_email_task.delay(str(user.id))
            log_event(
                user=user,
                action=AuditLog.Action.PASSWORD_RESET_REQUEST,
                request=request,
            )
        # Always the same response — never reveal whether an email
        # exists.
        return api_response(message="If that email is registered, a reset link " "has been sent.")


# --------------------------------------------------------------------- #
# POST /api/v1/auth/reset-password
# --------------------------------------------------------------------- #
class PasswordResetConfirmView(APIView):
    permission_classes = [AllowAny]
    throttle_classes = [AuthThrottle]

    @extend_schema(
        summary="Confirm a password reset",
        description="Sets a new password using the uid+token from the reset email link.",
        request=PasswordResetConfirmSerializer,
    )
    def post(self, request):
        serializer = PasswordResetConfirmSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        user = serializer.save()
        log_event(
            user=user,
            action=AuditLog.Action.PASSWORD_RESET,
            request=request,
        )
        return api_response(message="Password has been reset. You can now log in.")


# --------------------------------------------------------------------- #
# POST /api/v1/auth/verify-email
# --------------------------------------------------------------------- #
class EmailVerifyView(APIView):
    permission_classes = [AllowAny]
    throttle_classes = [AuthThrottle]

    @extend_schema(
        summary="Verify an email address",
        description="Confirms the 6-digit code sent to the user's email.",
        request=EmailVerifySerializer,
    )
    def post(self, request):
        serializer = EmailVerifySerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        user = serializer.validated_data["user"]
        user.mark_email_verified()
        log_event(
            user=user,
            action=AuditLog.Action.EMAIL_VERIFIED,
            request=request,
        )
        return api_response(message="Email verified successfully.")


# --------------------------------------------------------------------- #
# POST /api/v1/auth/resend-verification
# --------------------------------------------------------------------- #
class ResendVerificationView(APIView):
    permission_classes = [AllowAny]
    throttle_classes = [AuthThrottle]

    @extend_schema(
        summary="Resend the verification code",
        description="Sends a fresh 6-digit code, invalidating any previous one. "
        "Always returns the same message, to avoid revealing whether an "
        "account exists.",
        request=ResendVerificationSerializer,
    )
    def post(self, request):
        serializer = ResendVerificationSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        user = User.objects.filter(email__iexact=serializer.validated_data["email"]).first()
        if user and not user.email_verified:
            send_verification_email_task.delay(str(user.id))
        return api_response(
            message="If that email is registered and unverified, a new code has been sent."
        )


# --------------------------------------------------------------------- #
# GET/PUT /api/v1/users/me
# --------------------------------------------------------------------- #
class MeView(generics.RetrieveUpdateAPIView):
    serializer_class = UserSerializer
    permission_classes = [IsAuthenticated, IsAccountActive]

    def get_object(self):
        return self.request.user

    def retrieve(self, request, *args, **kwargs):
        return api_response(
            message="Profile retrieved.",
            data=self.get_serializer(request.user).data,
        )

    def update(self, request, *args, **kwargs):
        serializer = self.get_serializer(
            request.user,
            data=request.data,
            partial=True,
        )
        serializer.is_valid(raise_exception=True)
        serializer.save()
        return api_response(
            message="Profile updated.",
            data=serializer.data,
        )


# --------------------------------------------------------------------- #
# PUT /api/v1/users/password
# --------------------------------------------------------------------- #
class ChangePasswordView(APIView):
    permission_classes = [IsAuthenticated, IsAccountActive]

    @extend_schema(
        summary="Change password",
        description="Changes the logged-in user's password, given the current one.",
        request=ChangePasswordSerializer,
    )
    def put(self, request):
        serializer = ChangePasswordSerializer(
            data=request.data,
            context={"request": request},
        )
        serializer.is_valid(raise_exception=True)
        serializer.save()
        log_event(
            user=request.user,
            action=AuditLog.Action.PASSWORD_CHANGE,
            request=request,
        )
        return api_response(message="Password changed successfully.")


# --------------------------------------------------------------------- #
# /api/v1/admin/users — staff & role management (SDD §16.15)
# Admins create Content Editors (staff who handle images), suspend
# accounts, etc. Role escalation is restricted in the serializer.
# --------------------------------------------------------------------- #
class AdminUserViewSet(viewsets.ModelViewSet):
    serializer_class = AdminUserSerializer
    permission_classes = [IsAuthenticated, IsAdminOrAbove]
    queryset = User.objects.all().order_by("-created_at")
    filterset_fields = ["role", "account_status", "email_verified"]
    search_fields = ["email", "first_name", "last_name"]

    def get_permissions(self):
        # Deleting users is a Super Admin capability.
        if self.action == "destroy":
            return [IsAuthenticated(), IsSuperAdmin()]
        return super().get_permissions()

    def perform_create(self, serializer):
        user = serializer.save()
        log_event(
            user=self.request.user,
            action=AuditLog.Action.USER_CREATED,
            request=self.request,
            created_user=str(user.id),
            role=user.role,
        )

    def perform_update(self, serializer):
        old_role = serializer.instance.role
        user = serializer.save()
        if user.role != old_role:
            log_event(
                user=self.request.user,
                action=AuditLog.Action.ROLE_CHANGE,
                request=self.request,
                target_user=str(user.id),
                old_role=old_role,
                new_role=user.role,
            )

    def perform_destroy(self, instance):
        instance.delete()  # soft delete via BaseModel
