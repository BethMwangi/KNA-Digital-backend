"""
External download-link client — the source system keeps the purchasable
originals; after payment we exchange (refno, format) for a downloadable
URL through their API.

Integration point: in apps/downloads/views.py DownloadViewSet.link, replace
    url = storage_service.signed_url(variant.storage_path, expires_in=900)
with
    url = ExternalArchiveClient().get_download_url(
        refno=dl.asset.sync_record.external_refno,
        fmt=dl.variant_name,
    )
Everything else — entitlement checks, download counting, audit logging,
limits, expiry — stays exactly as built.
"""

import logging

import requests
from django.conf import settings

logger = logging.getLogger(__name__)


class ExternalArchiveError(Exception):
    pass


class ExternalArchiveClient:
    def __init__(self):
        self.base = getattr(settings, "LEGACY_ARCHIVE_BASE_URL", "").rstrip("/")
        self.api_key = getattr(settings, "LEGACY_ARCHIVE_API_KEY", "")

    def get_download_url(self, *, refno: str, fmt: str) -> str:
        """Exchange a purchased entitlement for a downloadable link.
        Align endpoint/fields with the provider's API contract on delivery;
        keep all such adjustments inside this class."""
        try:
            r = requests.post(
                f"{self.base}/downloads/request",
                json={"refno": refno, "format": fmt},
                headers={"X-Api-Key": self.api_key},
                timeout=30,
            )
            r.raise_for_status()
            url = r.json().get("download_url", "")
        except requests.RequestException as exc:
            logger.exception("External download request failed for %s/%s", refno, fmt)
            raise ExternalArchiveError(
                "The archive file service is temporarily unavailable. Please retry."
            ) from exc
        if not url:
            raise ExternalArchiveError("The archive did not return a download link.")
        return url
