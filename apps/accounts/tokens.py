"""
Signed, expiring tokens for email verification and password reset,
plus the transactional emails that deliver them (SDD §21).

Uses Django's built-in cryptographic token generator (stateless, no DB
table needed, invalidated automatically when the password or last_login
changes) — the same battle-tested mechanism as Django admin resets.
"""

from django.conf import settings
from django.contrib.auth.tokens import PasswordResetTokenGenerator, default_token_generator
from django.core.mail import send_mail
from django.utils.encoding import force_bytes
from django.utils.http import urlsafe_base64_decode, urlsafe_base64_encode


class EmailVerificationTokenGenerator(PasswordResetTokenGenerator):
    """Separate hash so a reset token can't be replayed as a verify token."""

    def _make_hash_value(self, user, timestamp):
        return f"{user.pk}{timestamp}{user.email_verified}"


email_verification_token = EmailVerificationTokenGenerator()
password_reset_token = default_token_generator


def encode_uid(user) -> str:
    return urlsafe_base64_encode(force_bytes(user.pk))


def decode_uid(uidb64: str):
    from .models import User

    try:
        uid = urlsafe_base64_decode(uidb64).decode()
        return User.objects.get(pk=uid)
    except (TypeError, ValueError, OverflowError, User.DoesNotExist):
        return None


# --------------------------------------------------------------------- #
# Transactional emails (SDD §21). Swap the console backend for SMTP or a
# provider (e.g. Resend, SES, Postmark) via env vars — no code changes.
# --------------------------------------------------------------------- #
def send_verification_email(user) -> None:
    token = email_verification_token.make_token(user)
    link = f"{settings.FRONTEND_URL}/verify-email?uid={encode_uid(user)}&token={token}"
    send_mail(
        subject="Verify your Kenya News Agency Archive account",
        message=(
            f"Hello {user.first_name},\n\n"
            f"Welcome to the KNA Digital Archive. Please verify your email:\n\n{link}\n\n"
            "If you did not create this account, you can ignore this email."
        ),
        from_email=settings.DEFAULT_FROM_EMAIL,
        recipient_list=[user.email],
        fail_silently=False,
    )


def send_password_reset_email(user) -> None:
    token = password_reset_token.make_token(user)
    link = f"{settings.FRONTEND_URL}/reset-password?uid={encode_uid(user)}&token={token}"
    send_mail(
        subject="Reset your password",
        message=(
            f"Hello {user.first_name},\n\n"
            f"We received a request to reset your password:\n\n{link}\n\n"
            "This link expires shortly. If you did not request this, ignore this email."
        ),
        from_email=settings.DEFAULT_FROM_EMAIL,
        recipient_list=[user.email],
        fail_silently=False,
    )
