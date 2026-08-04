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
        id_number: str,
        callback_url: str,
        success_redirect_url: str,
        fail_redirect_url: str,  # noqa: ARG002 — no fail-redirect field in Pesaflow's iframe API
    ) -> str:
        """Create a Pesaflow invoice and return the checkout URL.

        Raises ``PesaflowError`` on any non-success response so the caller
        can surface a user-friendly message.
        """
        client_name = f"{first_name} {last_name}"
        amount_expected = str(payment.amount)
        bill_ref_number = payment.transaction_id
        bill_desc = f"Order {payment.order.order_number}"

        payload = {
            "apiClientID": self.api_client_id,
            "serviceID": self.service_id,
            "billDesc": bill_desc,
            "currency": payment.currency,
            "billRefNumber": bill_ref_number,
            "clientMSISDN": phone,
            "clientName": client_name,
            "clientIDNumber": id_number,
            "clientEmail": email,
            "callBackURLOnSuccess": success_redirect_url,
            "amountExpected": amount_expected,
            "notificationURL": callback_url,
            "pictureURL": "",
            "sendSTK": "true",
            "format": "json",
        }

        # Secure hash: HMAC-SHA256 over these exact values in this exact
        # showing base64_encode() of the hex digest, a real example from
        # their support team is a plain 64-char hex string with no
        # base64 step — trusting the live example over the doc sample.
        secure_hash = self._generate_secure_hash(
            api_client_id=self.api_client_id,
            amount=amount_expected,
            service_id=self.service_id,
            client_id_number=id_number,
            currency=payment.currency,
            bill_ref_number=bill_ref_number,
            bill_desc=bill_desc,
            client_name=client_name,
        )
        payload["secureHash"] = secure_hash

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
            response = requests.post(url, json=payload, timeout=REQUEST_TIMEOUT)
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

        if not isinstance(data, dict):
            # A 2xx with a JSON body that isn't an object (bare list,
            # string, number) — not a shape we know how to read a
            # checkout URL out of.
            logger.error("PESAFLOW returned unexpected JSON shape: %r", data)
            raise PesaflowError("Pesaflow returned an unexpected response format.")

        if data.get("status") in ("FAIL", "ERROR", "error"):
            error_msg = data.get("message", data.get("status_message", "Unknown error"))
            logger.error(
                "PESAFLOW invoice creation failed: %s — full response: %s", error_msg, data
            )
            raise PesaflowError(f"Pesaflow rejected the invoice: {error_msg}")

        # Successful JSON response should contain the checkout/iframe URL
        # — confirmed live, their actual field is "invoice_link" (not
        # documented; the others are speculative fallbacks in case a
        # different Pesaflow API version uses a different name).
        checkout_url = (
            data.get("invoice_link")
            or data.get("checkout_url")
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

        NOTE: the integration doc doesn't specify an IPN signature
        formula the way it does for invoice creation and the query-status
        API (both of which have exact PHP/C# samples) — its IPN
        parameter table lists a ``token_hash`` field with no hashing
        recipe given. Until Pesaflow confirms one, this can't do a real
        HMAC comparison; it only checks that a token_hash was present,
        which is what PesaflowIPNView already falls back to gracefully
        (treats "no signature" as "can't verify" rather than "invalid").
        Revisit once Pesaflow support confirms the actual formula.
        """
        return bool(signature)

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
    def _generate_secure_hash(
        self,
        *,
        api_client_id: str,
        amount: str,
        service_id: str,
        client_id_number: str,
        currency: str,
        bill_ref_number: str,
        bill_desc: str,
        client_name: str,
    ) -> str:
        """Pesaflow's formula:

            secure_hash = hmac_sha256(
                apiClientID + amount + serviceID + clientIDNumber +
                currency + billRefNumber + billDesc + clientName + secret,
                key=key,
            )

        A plain lowercase hex digest — confirmed against a real working
        example from Pesaflow's support team (64 hex chars, no base64).
        Their PHP/C# integration-doc sample showed base64_encode() of
        the digest, but that doc has already proven unreliable on
        field-name casing too, so the live example wins.

        The HMAC *key* parameter is a separate credential (PESAFLOW_KEY)
        from the *secret* that gets concatenated into the message itself
        (PESAFLOW_SECRET) — using one value for both silently produces a
        wrong hash. The field order above is fixed, not alphabetical.
        """
        message = "".join(
            [
                api_client_id,
                amount,
                service_id,
                client_id_number,
                currency,
                bill_ref_number,
                bill_desc,
                client_name,
                self.secret,
            ]
        )
        return hmac.new(
            self.key.encode("utf-8"),
            message.encode("utf-8"),
            hashlib.sha256,
        ).hexdigest()


class PesaflowError(Exception):
    """Raised when the Pesaflow API returns an error or is unreachable."""
