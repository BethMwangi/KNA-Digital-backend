"""
Scheduled sync — once the source exposes their API, point the env vars at
it and add this to Celery beat. Until then, sync_legacy handles JSON dumps.
"""

import logging

import requests
from celery import shared_task
from django.conf import settings

from .services import sync_categories, sync_images

logger = logging.getLogger(__name__)


@shared_task(bind=True, max_retries=3, default_retry_delay=300)
def sync_from_source_api(self):
    base = getattr(settings, "LEGACY_ARCHIVE_BASE_URL", "")
    if not base:
        logger.info("LEGACY_ARCHIVE_BASE_URL not configured — skipping scheduled sync.")
        return
    headers = {"X-Api-Key": getattr(settings, "LEGACY_ARCHIVE_API_KEY", "")}
    try:
        cats = requests.get(f"{base}/categories", headers=headers, timeout=60).json()
        sync_categories(cats)
        page = 1
        while True:
            r = requests.get(
                f"{base}/images",
                params={"page": page, "page_size": 500},
                headers=headers,
                timeout=120,
            )
            r.raise_for_status()
            batch = r.json()
            records = batch.get("results", batch) if isinstance(batch, dict) else batch
            if not records:
                break
            run = sync_images(records)
            logger.info(
                "Image sync page %s: +%s ~%s =%s !%s",
                page,
                run.created,
                run.updated,
                run.skipped,
                run.conflicts,
            )
            if isinstance(batch, dict) and not batch.get("next"):
                break
            if not isinstance(batch, dict):
                break
            page += 1
    except requests.RequestException as exc:
        raise self.retry(exc=exc) from exc
