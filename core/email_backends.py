"""
Resend HTTP-API email backend.

Why this exists: most PaaS hosts (Render, Heroku, Railway...) block or
silently drop outbound SMTP (port 587/25/465) to prevent spam abuse.
Confirmed on this deployment — a registration request hung for exactly
Gunicorn's 30s worker timeout trying to reach smtp.gmail.com, killing
the request (500) even though the same credentials connect from a
normal network in ~3s. HTTPS is never blocked, so a transactional email
provider's REST API sidesteps the problem entirely. Resend's free tier
(100/day, 3,000/month) is plenty for order receipts + password resets.

Drop-in: implements Django's BaseEmailBackend, so every existing
send_mail()/EmailMultiAlternatives call in the codebase (accounts/tokens.py,
payments/emails.py) works unchanged — only settings.EMAIL_BACKEND changes.
"""

import logging

import requests
from django.core.mail.backends.base import BaseEmailBackend

logger = logging.getLogger(__name__)

RESEND_API_URL = "https://api.resend.com/emails"


class ResendEmailBackend(BaseEmailBackend):
    def send_messages(self, email_messages) -> int:
        if not email_messages:
            return 0
        from django.conf import settings

        api_key = getattr(settings, "RESEND_API_KEY", "")
        if not api_key:
            if not self.fail_silently:
                raise ValueError("RESEND_API_KEY is not set.")
            logger.warning("ResendEmailBackend: RESEND_API_KEY not set, skipping %d message(s)")
            return 0

        sent = 0
        for message in email_messages:
            payload = {
                "from": message.from_email,
                "to": list(message.to),
                "subject": message.subject,
                "text": message.body,
            }
            if message.cc:
                payload["cc"] = list(message.cc)
            if message.bcc:
                payload["bcc"] = list(message.bcc)
            try:
                r = requests.post(
                    RESEND_API_URL,
                    headers={"Authorization": f"Bearer {api_key}"},
                    json=payload,
                    timeout=15,
                )
                r.raise_for_status()
                sent += 1
                logger.info("Resend: sent %r to %s", message.subject, message.to)
            except requests.RequestException as exc:
                logger.error(
                    "Resend send failed for %r to %s: %s", message.subject, message.to, exc
                )
                if not self.fail_silently:
                    raise
        return sent
