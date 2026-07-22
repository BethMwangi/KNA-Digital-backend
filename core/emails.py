"""Send a branded HTML email (with a plain-text fallback) from a
core/templates/emails/*.html template — the shared helper every
transactional email in the project goes through."""

from django.conf import settings
from django.core.mail import EmailMultiAlternatives
from django.template.loader import render_to_string


def send_templated_email(
    *,
    subject: str,
    template_name: str,
    context: dict,
    recipient_list: list[str],
    text_body: str,
    from_email: str | None = None,
) -> None:
    html_body = render_to_string(
        f"emails/{template_name}", {**context, "frontend_url": settings.FRONTEND_URL}
    )
    message = EmailMultiAlternatives(
        subject=subject,
        body=text_body,
        from_email=from_email or settings.DEFAULT_FROM_EMAIL,
        to=recipient_list,
    )
    message.attach_alternative(html_body, "text/html")
    message.send(fail_silently=False)
