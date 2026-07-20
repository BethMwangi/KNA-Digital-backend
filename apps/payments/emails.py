"""
Transactional emails for payments — same plain send_mail style as
apps/accounts/tokens.py. Swap EMAIL_BACKEND/EMAIL_HOST for Gmail SMTP or
any other provider via env vars only; no code changes here.
"""

from django.conf import settings
from django.core.mail import send_mail


def send_payment_success_email(order) -> None:
    lines = [
        f"Hello {order.user.first_name},",
        "",
        f"Your payment for order {order.order_number} was successful. " "Here's what you bought:",
        "",
    ]
    for item in order.items.select_related("asset", "license"):
        lines.append(
            f"  - {item.asset_title_snapshot} "
            f"({item.license.name} license) — KES {item.price_at_purchase}"
        )
    lines += [
        "",
        f"Total paid: KES {order.total}",
        "",
        f"Your downloads are ready in your account: {settings.FRONTEND_URL}/account/downloads",
        "",
        "Thank you for supporting the Kenya News Agency Digital Archive.",
    ]
    send_mail(
        subject=f"Payment received — order {order.order_number}",
        message="\n".join(lines),
        from_email=settings.DEFAULT_FROM_EMAIL,
        recipient_list=[order.user.email],
        fail_silently=False,
    )


def send_payment_failed_email(order) -> None:
    message = (
        f"Hello {order.user.first_name},\n\n"
        f"Your payment for order {order.order_number} (KES {order.total}) "
        "did not go through.\n\n"
        f"No charge was made. You can try again from your cart:\n"
        f"{settings.FRONTEND_URL}/checkout\n\n"
        "If this keeps happening, reply to this email and we'll help you out."
    )
    send_mail(
        subject=f"Payment unsuccessful — order {order.order_number}",
        message=message,
        from_email=settings.DEFAULT_FROM_EMAIL,
        recipient_list=[order.user.email],
        fail_silently=False,
    )
