"""
Transactional emails for payments — branded HTML templates via
core.emails.send_templated_email (core/templates/emails/*.html), with a
plain-text fallback for clients that don't render HTML.
"""

from django.conf import settings

from core.emails import send_templated_email


def send_payment_success_email(order) -> None:
    order_items = list(order.items.select_related("asset", "license"))
    downloads_url = f"{settings.FRONTEND_URL}/account/downloads"

    text_lines = [
        f"Hello {order.user.first_name},",
        "",
        f"Your payment for order {order.order_number} was successful. Here's what you bought:",
        "",
    ]
    for item in order_items:
        text_lines.append(
            f"  - {item.asset_title_snapshot} ({item.license.name} license) — KES {item.price_at_purchase}"
        )
    text_lines += [
        "",
        f"Total paid: KES {order.total}",
        "",
        f"Your downloads are ready in your account: {downloads_url}",
        "",
        "Thank you for supporting the Kenya News Agency Digital Archive.",
    ]

    send_templated_email(
        subject=f"Payment received — order {order.order_number}",
        template_name="payment_success.html",
        context={
            "first_name": order.user.first_name,
            "order_number": order.order_number,
            "total": order.total,
            "downloads_url": downloads_url,
            "items": [
                {
                    "title": item.asset_title_snapshot,
                    "license": item.license.name,
                    "price": item.price_at_purchase,
                }
                for item in order_items
            ],
        },
        recipient_list=[order.user.email],
        text_body="\n".join(text_lines),
    )


def send_payment_failed_email(order) -> None:
    checkout_url = f"{settings.FRONTEND_URL}/checkout"
    text_body = (
        f"Hello {order.user.first_name},\n\n"
        f"Your payment for order {order.order_number} (KES {order.total}) did not go through.\n\n"
        f"No charge was made. You can try again from your cart:\n{checkout_url}\n\n"
        "If this keeps happening, reply to this email and we'll help you out."
    )
    send_templated_email(
        subject=f"Payment unsuccessful — order {order.order_number}",
        template_name="payment_failed.html",
        context={
            "first_name": order.user.first_name,
            "order_number": order.order_number,
            "total": order.total,
            "checkout_url": checkout_url,
        },
        recipient_list=[order.user.email],
        text_body=text_body,
    )
