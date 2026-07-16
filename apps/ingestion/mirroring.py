"""
Thumbnail mirroring — every variant file lives in OUR public bucket.

Mirror-first policy: the source server is contacted only while seeding.
fetch_and_store() downloads a thumbnail and saves it into "public_media"
storage DURING sync, so a record is only ever stored (and acked) with
its files already in our bucket — the storefront never links the source
server. A failed download fails the whole record: it is not acked, and
the feed re-delivers it on a later run.

mirror_variant() repairs pre-existing rows that still hold external URLs
from before this policy (see the mirror_thumbnails command).

settings.MIRROR_THUMBNAILS=False is an emergency fallback only: sync
stores the source URL directly instead of downloading.
"""

import hashlib
import logging
import time

import requests
from django.core.files.base import ContentFile
from django.core.files.storage import storages

logger = logging.getLogger(__name__)

MAX_THUMB_BYTES = 10 * 1024 * 1024  # sanity cap: previews are small


def fetch_and_store(source_url: str, *, asset_number: str, variant_name: str) -> dict:
    """Download one thumbnail into our public bucket. Returns AssetVariant
    field values pointing at OUR storage. Raises on any failure so the
    caller's transaction rolls back and the record is retried later."""
    started = time.monotonic()
    logger.info("GET %s", source_url)
    r = requests.get(source_url, timeout=60)
    r.raise_for_status()
    content = r.content
    if len(content) > MAX_THUMB_BYTES:
        raise ValueError(f"thumbnail unexpectedly large ({len(content)} bytes): {source_url}")

    mime = r.headers.get("Content-Type", "image/jpeg").split(";")[0].strip() or "image/jpeg"
    ext = {"image/png": "png", "image/webp": "webp"}.get(mime, "jpg")
    path = f"assets/{asset_number}/{variant_name}.{ext}"
    saved_path = storages["public_media"].save(path, ContentFile(content))
    logger.info(
        "stored %s (%d bytes, %s) in %.1fs",
        saved_path,
        len(content),
        mime,
        time.monotonic() - started,
    )
    return {
        "storage_path": saved_path,
        "mime_type": mime,
        "file_size": len(content),
        "checksum": hashlib.sha256(content).hexdigest(),
    }


def mirror_variant(variant_id: str) -> bool:
    """Repair one pre-policy AssetVariant that still hotlinks the source:
    download its file into our bucket and repoint storage_path. Never
    raises — failures are logged and the row is left for a re-run."""
    from apps.assets.models import AssetVariant

    variant = AssetVariant.objects.select_related("asset").filter(id=variant_id).first()
    if variant is None or not variant.storage_path.startswith(("http://", "https://")):
        return False  # deleted, or already in our bucket

    try:
        values = fetch_and_store(
            variant.storage_path,
            asset_number=variant.asset.asset_number,
            variant_name=variant.variant_name,
        )
    except Exception:  # noqa: BLE001
        logger.exception("Mirror failed for variant %s (%s)", variant_id, variant.storage_path)
        return False

    for field, value in values.items():
        setattr(variant, field, value)
    variant.save(update_fields=[*values.keys(), "updated_at"])
    return True
