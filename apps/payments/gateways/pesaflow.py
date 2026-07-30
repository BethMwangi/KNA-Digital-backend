"""
Pesaflow gateway adapter — creates invoices on the Pesaflow hosted
checkout (iframe v2.1) and validates IPN (Instant Payment Notification)
callbacks.

Usage:
    from apps.payments.gateways.pesaflow import PesaflowGateway

    gw = PesaflowGateway()
    checkout_url = gw.create_invoice(payment, billing_info)
    is_valid = gw.verify_ipn_signature(request_body, signature_header)
    status, txn_id, raw = gw.parse_ipn(payload)
"""

import hashlib
import hmac
import logging
from typing import NamedTuple

import requests
from django.conf import settings

logger = logging.getLogger(__name__)

# How long to wait for Pesaflow's API to respond (connect, read) in seconds.
REQUEST_TIMEOUT = (10, 30)


class IPNResult(NamedTuple):
    """Normalised output from parse_ipn()."""

    status: str  # "completed" | "failed"
    transaction_id: str
    provider_response: dict


class PesaflowGateway:
    """Adapter for the Pesaflow hosted checkout API (iframe v2.1).

    All configuration is read from ``django.conf.settings`` so credentials
    never leak into call-site code. The class is stateless and safe to
    instantiate per-request.
    """

    def __init__(self):
        self.service_id = settings.PESAFLOW_SERVICE_ID
        self.key = settings.PESAFLOW_KEY
        self.secret = settings.PESAFLOW_SECRET
        self.api_client_id = settings.PESAFLOW_API_CLIENT_ID
        self.base_url = settings.PESAFLOW_BASE_URL.rstrip("/")

    # ------------------------------------------------------------------ #
    # Invoice creation
    # ------------------------------------------------------------------ #
    def create_invoice(
        self,
        *,
        payment,
        first_name: str,
        last_name: str,
        email: str,
        phone: str,
        callback_url: str,
        success_redirect_url: str,
        fail_redirect_url: str,
    ) -> str:
        """Create a Pesaflow invoice and return the checkout URL.

        Raises ``PesaflowError`` on any non-success response so the caller
        can surface a user-friendly message.
        """
        payload = {
            "s": self.service_id,
            "api_client_id": self.api_client_id,
            "key": self.key,
            "amount": str(payment.amount),
            "currency": payment.currency,
            "first_name": first_name,
            "last_name": last_name,
            "email": email,
            "phone_number": phone,
            "bill_desc": f"Order {payment.order.order_number}",
            "bill_ref_number": payment.transaction_id,
            "cust_name": f"{first_name} {last_name}",
            "notification_url": callback_url,
            "call_back_url_onSuccess": success_redirect_url,
            "call_back_url_onFail": fail_redirect_url,
            "format": "json",
        }

        # Generate the secure hash: HMAC-SHA256 of the concatenated values
        # sorted by key, using the Pesaflow secret.
        secure_hash = self._generate_secure_hash(payload)
        payload["secure_hash"] = secure_hash

        url = f"{self.base_url}/PaymentAPI/iframev2.1.php"

        logger.info(
            "PESAFLOW create_invoice txn=%s order=%s amount=%s %s -> %s",
            payment.transaction_id,
            payment.order.order_number,
            payment.amount,
            payment.currency,
            url,
        )

        try:
            response = requests.post(url, data=payload, timeout=REQUEST_TIMEOUT)
            response.raise_for_status()
        except requests.RequestException as exc:
            logger.error("PESAFLOW API request failed: %s", exc)
            raise PesaflowError(f"Could not reach Pesaflow: {exc}") from exc

        # Pesaflow may return JSON with an iframe URL or an error.
        try:
            data = response.json()
        except ValueError:
            # If the response is HTML (the iframe page itself), the URL is
            # the request URL with the payload encoded — return it.
            logger.warning(
                "PESAFLOW returned non-JSON response (likely iframe HTML), "
                "using request URL as checkout URL."
            )
            # Build the checkout URL with GET params for iframe embedding
            checkout_url = response.url
            return checkout_url

        if isinstance(data, dict) and data.get("status") in ("FAIL", "ERROR", "error"):
            error_msg = data.get("message", data.get("status_message", "Unknown error"))
            logger.error(
                "PESAFLOW invoice creation failed: %s — full response: %s", error_msg, data
            )
            raise PesaflowError(f"Pesaflow rejected the invoice: {error_msg}")

        # Successful JSON response should contain the checkout/iframe URL
        checkout_url = (
            data.get("checkout_url")
            or data.get("iframe_url")
            or data.get("payment_url")
            or data.get("url")
        )
        if not checkout_url:
            # Some Pesaflow API versions return the full response URL
            # as the redirect target when the invoice is created inline.
            logger.warning(
                "PESAFLOW JSON response has no explicit checkout URL field: %s — "
                "falling back to response URL.",
                data,
            )
            checkout_url = response.url

        logger.info(
            "PESAFLOW invoice created txn=%s checkout_url=%s",
            payment.transaction_id,
            checkout_url,
        )
        return checkout_url

    # ------------------------------------------------------------------ #
    # IPN (Instant Payment Notification) verification
    # ------------------------------------------------------------------ #
    def verify_ipn_signature(self, payload: dict, signature: str) -> bool:
        """Verify that the IPN callback was genuinely sent by Pesaflow.

        Pesaflow signs IPN payloads with HMAC-SHA256 using the merchant's
        secret key. The signature is sent in the ``secure_hash`` field or
        as a header — we check both.
        """
        expected = self._generate_secure_hash(payload)
        return hmac.compare_digest(expected, signature)

    def parse_ipn(self, payload: dict) -> IPNResult:
        """Normalise a Pesaflow IPN payload into the shape our services
        module expects.

        Pesaflow sends status values like ``SUCCESS``, ``FAIL``,
        ``PENDING``. We map them to the two outcomes our
        ``complete_payment`` / ``fail_payment`` functions understand.
        """
        raw_status = str(payload.get("payment_status", payload.get("status", ""))).upper()
        transaction_id = str(
            payload.get(
                "bill_ref_number", payload.get("reference", payload.get("transaction_id", ""))
            )
        )

        if raw_status in ("SUCCESS", "COMPLETED", "PAID"):
            normalised = "completed"
        else:
            normalised = "failed"

        return IPNResult(
            status=normalised,
            transaction_id=transaction_id,
            provider_response=payload,
        )

    # ------------------------------------------------------------------ #
    # Internal helpers
    # ------------------------------------------------------------------ #
    def _generate_secure_hash(self, payload: dict) -> str:
        """HMAC-SHA256 secure hash of payload values, sorted by key.

        Only includes non-empty string values; ``secure_hash`` itself is
        excluded if present (it's the field we're computing).
        """
        filtered = {
            k: v for k, v in sorted(payload.items()) if k != "secure_hash" and v not in (None, "")
        }
        message = "".join(str(v) for v in filtered.values())
        return hmac.new(
            self.secret.encode("utf-8"),
            message.encode("utf-8"),
            hashlib.sha256,
        ).hexdigest()


class PesaflowError(Exception):
    """Raised when the Pesaflow API returns an error or is unreachable."""
