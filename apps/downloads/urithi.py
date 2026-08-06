import logging
from decimal import Decimal
from typing import Any

import requests
from django.conf import settings

from .models import Download

logger = logging.getLogger(__name__)


REQUEST_TIMEOUT = (10, 30)


class UrithiDownloadLinkError(Exception):
    pass


def sync_order_download_links(order, payment) -> None:
    for download in order.downloads.select_related("asset", "asset__metadata", "order"):
        try:
            sync_download_link(download, payment)
        except Exception as exc:  # noqa: BLE001
            download.external_last_error = str(exc)
            download.save(update_fields=["external_last_error", "updated_at"])
            logger.exception(
                "URITHI download-link sync failed download=%s order=%s",
                download.id,
                order.order_number,
            )


def sync_download_link(download: Download, payment) -> Download:
    payload = build_download_link_payload(download, payment)
    endpoint = settings.URITHI_DOWNLOAD_LINK_ENDPOINT

    try:
        response = requests.post(endpoint, json=payload, timeout=REQUEST_TIMEOUT)
        response.raise_for_status()
        data = response.json()
    except (requests.RequestException, ValueError) as exc:
        raise UrithiDownloadLinkError(f"Could not request Urithi download link: {exc}") from exc

    status = data.get("status") or data.get("data", {}).get("status", "")
    body = data.get("data") if isinstance(data.get("data"), dict) else data
    download_link = body.get("download_link", "")

    if not status:
        raise UrithiDownloadLinkError(f"Urithi response missing status: {data}")

    if status == "success" and body.get("status"):
        status = body["status"]

    update_fields = [
        "external_download_status",
        "external_download_link",
        "external_download_counts",
        "external_payload",
        "external_response",
        "external_last_error",
        "updated_at",
    ]
    download.external_download_status = str(status)
    download.external_download_link = str(download_link or "")
    download.external_download_counts = _as_int(body.get("download_counts"))
    download.external_payload = payload
    download.external_response = data
    download.external_last_error = ""

    max_downloads = _as_int(body.get("max_downloads"))
    if max_downloads is not None:
        download.max_downloads = max_downloads
        update_fields.append("max_downloads")

    download.save(update_fields=update_fields)
    logger.info(
        "URITHI download-link synced download=%s status=%s has_link=%s",
        download.id,
        download.external_download_status,
        bool(download.external_download_link),
    )
    return download


def build_download_link_payload(download: Download, payment) -> dict[str, Any]:
    response = payment.provider_response if isinstance(payment.provider_response, dict) else {}
    asset = download.asset
    legacy_image_id = getattr(getattr(asset, "metadata", None), "legacy_image_id", None)
    image_id = str(legacy_image_id or asset.asset_number or asset.id)

    return {
        "image_id": image_id,
        "payment_channel": _first(response, "payment_channel", "payment_mode", "channel")
        or payment.provider,
        "client_invoice_ref": _first(response, "client_invoice_ref", "bill_ref_number")
        or payment.transaction_id,
        "payment_reference": _first(
            response,
            "payment_reference",
            "reference",
            "receipt_number",
            "transaction_id",
        )
        or payment.transaction_id,
        "currency": _first(response, "currency") or payment.currency,
        "amount_paid": _decimal_to_string(
            _first(response, "amount_paid", "amount") or payment.amount
        ),
        "invoice_amount": _decimal_to_string(
            _first(response, "invoice_amount", "amountExpected") or download.order.total
        ),
        "transaction_status": _first(response, "transaction_status", "payment_status", "status")
        or payment.status,
        "invoice_number": _first(response, "invoice_number", "invoiceNumber")
        or download.order.order_number,
        "payment_date": _first(response, "payment_date", "paymentDate")
        or (payment.paid_at.isoformat() if payment.paid_at else ""),
    }


def _first(data: dict[str, Any], *keys: str) -> Any:
    for key in keys:
        value = data.get(key)
        if value not in (None, ""):
            return value
    return None


def _decimal_to_string(value: Any) -> str:
    if isinstance(value, Decimal):
        return str(value)
    return str(value)


def _as_int(value: Any) -> int | None:
    if value in (None, ""):
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None
