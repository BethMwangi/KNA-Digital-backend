"""
Live-feed client. All endpoint details come from environment variables
(URITHI_BASE_URL, URITHI_LIST_PATH, URITHI_ACK_PATH) so nothing about the
source API is committed to the repository — see .env.example.

Contract: the server tracks acknowledgements — once a record is acked,
the next list call returns fresh records. So the loop is:
store durably -> ack -> repeat. NEVER ack before the DB commit.
"""

import logging
import time

import requests
from django.conf import settings

logger = logging.getLogger(__name__)


class UrithiError(Exception):
    pass


class UrithiClient:
    def __init__(self):
        base = (getattr(settings, "URITHI_BASE_URL", "") or "").rstrip("/")
        list_path = getattr(settings, "URITHI_LIST_PATH", "") or ""
        ack_path = getattr(settings, "URITHI_ACK_PATH", "") or ""
        if not (base and list_path and ack_path):
            raise UrithiError(
                "URITHI_BASE_URL, URITHI_LIST_PATH and URITHI_ACK_PATH must be "
                "set in the environment (kept out of the repo; see .env.example)."
            )
        self.list_url = f"{base}/{list_path.lstrip('/')}"
        self.ack_url = f"{base}/{ack_path.lstrip('/')}"
        self.session = requests.Session()

    def fetch_batch(self) -> list[dict]:
        """Returns the next batch as a list of records (empty when caught up)."""
        started = time.monotonic()
        logger.info("GET %s", self.list_url)
        try:
            r = self.session.get(self.list_url, timeout=60)
            r.raise_for_status()
            data = r.json()
        except (requests.RequestException, ValueError) as exc:
            raise UrithiError(f"list endpoint failed: {exc}") from exc
        elapsed = time.monotonic() - started
        if not data:
            logger.info("<- HTTP %s, empty response in %.1fs", r.status_code, elapsed)
            return []
        # Response is a dict keyed by their numeric row id; values are records.
        if isinstance(data, dict):
            records = [rec for rec in data.values() if isinstance(rec, dict)]
        else:
            records = [rec for rec in data if isinstance(rec, dict)]
        logger.info(
            "<- HTTP %s, %d records (%d bytes) in %.1fs",
            r.status_code,
            len(records),
            len(r.content),
            elapsed,
        )
        return records

    def ack(self, image_id: str, response_id: str) -> None:
        """Acknowledge one durably-stored record. If their endpoint expects
        form-encoded rather than JSON, flip the payload kwarg here — keep
        all wire-format tweaks inside this method."""
        payload = {"image_id": image_id, "response_id": response_id}
        started = time.monotonic()
        logger.info("POST %s %s", self.ack_url, payload)
        try:
            r = self.session.post(self.ack_url, json=payload, timeout=30)
            r.raise_for_status()
        except requests.RequestException as exc:
            raise UrithiError(f"ack failed for {image_id}: {exc}") from exc
        logger.info(
            "<- HTTP %s in %.1fs: %s",
            r.status_code,
            time.monotonic() - started,
            (r.text or "")[:200].strip(),
        )
