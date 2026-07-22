"""Send a branded HTML email (with a plain-text fallback) from a
core/templates/emails/*.html template — the shared helper every
transactional email in the project goes through."""

from django.conf import settings
from django.contrib.staticfiles.storage import staticfiles_storage
from django.core.mail import EmailMultiAlternatives
from django.template.loader import render_to_string


def _logo_url() -> str | None:
    """Absolute URL for the email header logo, or None if the asset isn't
    there. Production uses whitenoise's manifest static storage, which
    raises if a referenced file is missing from the build — so a renamed
    or deleted logo must never be allowed to take down transactional
    email. Callers render a text wordmark fallback when this is None."""
    try:
        return settings.BACKEND_URL + staticfiles_storage.url("emails/logo.png")
    except ValueError:
        return None


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
        f"emails/{template_name}",
        {
            **context,
            "frontend_url": settings.FRONTEND_URL,
            "logo_url": _logo_url(),
        },
    )
    message = EmailMultiAlternatives(
        subject=subject,
        body=text_body,
        from_email=from_email or settings.DEFAULT_FROM_EMAIL,
        to=recipient_list,
    )
    message.attach_alternative(html_body, "text/html")
    message.send(fail_silently=False)
