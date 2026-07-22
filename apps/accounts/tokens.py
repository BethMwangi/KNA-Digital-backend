"""
Signed, expiring tokens for email verification and password reset,
plus the transactional emails that deliver them (SDD §21).

Uses Django's built-in cryptographic token generator (stateless, no DB
table needed, invalidated automatically when the password or last_login
changes) — the same battle-tested mechanism as Django admin resets.
"""

from django.conf import settings
from django.contrib.auth.tokens import PasswordResetTokenGenerator, default_token_generator
from django.utils.encoding import force_bytes
from django.utils.http import urlsafe_base64_decode, urlsafe_base64_encode

from core.emails import send_templated_email


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
# Transactional emails (SDD §21). Called from apps/accounts/tasks.py,
# off the request path — see that module for why. Swap EMAIL_BACKEND via
# env var (console / Resend / SMTP) — no code changes needed here.
# --------------------------------------------------------------------- #
def send_verification_email(user) -> None:
    token = email_verification_token.make_token(user)
    # Path must match the frontend's actual route (/auth/verify, confirmed
    # live) — NOT /verify-email, which 404s. Frontend routes changed once
    # already; if this starts 404ing again, re-check with the frontend team
    # before assuming the backend link format is wrong.
    link = f"{settings.FRONTEND_URL}/auth/verify?uid={encode_uid(user)}&token={token}"
    send_templated_email(
        subject="Verify your Kenya News Agency Archive account",
        template_name="verify_email.html",
        context={"first_name": user.first_name, "verify_url": link},
        recipient_list=[user.email],
        text_body=(
            f"Hello {user.first_name},\n\n"
            f"Welcome to the KNA Digital Archive. Please verify your email:\n\n{link}\n\n"
            "If you did not create this account, you can ignore this email."
        ),
    )


def send_password_reset_email(user) -> None:
    token = password_reset_token.make_token(user)
    # Path must match the frontend's actual route (/auth/reset, confirmed
    # live) — NOT /reset-password, which 404s.
    link = f"{settings.FRONTEND_URL}/auth/reset?uid={encode_uid(user)}&token={token}"
    send_templated_email(
        subject="Reset your password",
        template_name="password_reset.html",
        context={"first_name": user.first_name, "reset_url": link},
        recipient_list=[user.email],
        text_body=(
            f"Hello {user.first_name},\n\n"
            f"We received a request to reset your password:\n\n{link}\n\n"
            "This link expires shortly. If you did not request this, ignore this email."
        ),
    )
