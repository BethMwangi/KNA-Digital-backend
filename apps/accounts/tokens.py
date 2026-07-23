"""
Signed, expiring tokens for email verification and password reset,
plus the transactional emails that deliver them (SDD §21).

Uses Django's built-in cryptographic token generator (stateless, no DB
table needed, invalidated automatically when the password or last_login
changes) — the same battle-tested mechanism as Django admin resets.
"""

import secrets
from datetime import timedelta

from django.conf import settings
from django.contrib.auth.tokens import default_token_generator
from django.utils import timezone
from django.utils.encoding import force_bytes
from django.utils.http import urlsafe_base64_decode, urlsafe_base64_encode

from core.emails import send_templated_email

password_reset_token = default_token_generator

VERIFICATION_CODE_TTL = timedelta(minutes=30)


def generate_verification_code() -> str:
    """6-digit numeric OTP. `secrets` (not `random`) since this gates
    account access, same standard as password reset tokens."""
    return f"{secrets.randbelow(1_000_000):06d}"


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
# Transactional emails  Called from apps/accounts/tasks.py,
# off the request path — see that module for why. Swap EMAIL_BACKEND via
# env var (console / Resend / SMTP) — no code changes needed here.
# --------------------------------------------------------------------- #
def send_verification_email(user) -> None:
    # Code-based,
    # type 6 digits in; nothing about it can go stale.
    code = generate_verification_code()
    user.email_verification_code = code
    user.email_verification_code_expires_at = timezone.now() + VERIFICATION_CODE_TTL
    user.save(update_fields=["email_verification_code", "email_verification_code_expires_at"])
    send_templated_email(
        subject="Verify your Urithi Archive account",
        template_name="verify_email.html",
        context={"first_name": user.first_name, "code": code},
        recipient_list=[user.email],
        text_body=(
            f"Hello {user.first_name},\n\n"
            f"Welcome to Urithi Digital Archive. Your verification code is:\n\n{code}\n\n"
            "This code expires in 30 minutes. If you did not create this account, "
            "you can ignore this email."
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
