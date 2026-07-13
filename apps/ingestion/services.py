"""
Sync services — the heart of the ingestion layer.

sync_categories(): upserts LegacyCodeMap + our Category/Collection rows.
  Main categories → Collections, subcategories → Categories (see ADR note:
  the legacy main/sub pairing is per-image, not a tree — sub code 1
  'Presidential' appears under different mains in real data, so forcing
  Category.parent would corrupt. Two independent dimensions instead.)

sync_images(): idempotent upsert keyed on external_id.
  new record            → create asset + metadata + tags + variants
  checksum changed      → source edited it → re-map (unless sync_locked)
  checksum unchanged    → skip
  sync_locked + changed → conflict logged, local curation preserved
"""

import logging
import uuid

from django.db import transaction
from django.utils import timezone
from django.utils.text import slugify

from apps.assets.models import (
    AssetMetadata,
    AssetVariant,
    Category,
    Collection,
    DigitalAsset,
    Tag,
)

from . import normalizers as nz
from .models import AssetSyncRecord, LegacyCodeMap, SyncRun

logger = logging.getLogger(__name__)


# --------------------------------------------------------------------- #
# Categories
# --------------------------------------------------------------------- #
def _unique_slug(model, base: str) -> str:
    slug = slugify(base)[:95] or "item"
    candidate, n = slug, 2
    while model.objects.filter(slug=candidate).exists():
        candidate = f"{slug}-{n}"
        n += 1
    return candidate


def sync_categories(records: list[dict]) -> SyncRun:
    run = SyncRun.objects.create(kind=SyncRun.Kind.CATEGORIES, total=len(records))
    for rec in records:
        try:
            item_type = rec["ItemType"]
            code = int(rec["itemCode"])
            name = nz.clean_text(rec["ItemDescription"])
            if item_type not in LegacyCodeMap.ItemType.values:
                run.skipped += 1
                continue

            mapping = LegacyCodeMap.objects.filter(item_type=item_type, code=code).first()
            if mapping:
                # Renamed at source? Update our side too.
                if mapping.description != name:
                    target = mapping.target
                    if target is not None:
                        target.name = name
                        target.save(update_fields=["name", "updated_at"])
                    mapping.description = name
                    mapping.save(update_fields=["description", "updated_at"])
                    run.updated += 1
                else:
                    run.skipped += 1
                continue

            if item_type == LegacyCodeMap.ItemType.MAIN:
                target, _ = Collection.objects.get_or_create(
                    name=name, defaults={"slug": _unique_slug(Collection, name)}
                )
                LegacyCodeMap.objects.create(
                    item_type=item_type, code=code, description=name, collection=target
                )
            else:
                target, _ = Category.objects.get_or_create(
                    name=name,
                    defaults={"slug": _unique_slug(Category, name), "code": str(code)},
                )
                LegacyCodeMap.objects.create(
                    item_type=item_type, code=code, description=name, category=target
                )
            run.created += 1
        except Exception as exc:  # noqa: BLE001
            logger.exception("Category sync failed for %s", rec)
            run.errors.append({"record": rec, "error": str(exc)})
    run.finished_at = timezone.now()
    run.save()
    return run


# --------------------------------------------------------------------- #
# Images
# --------------------------------------------------------------------- #
def _resolve(item_type: str, code) -> LegacyCodeMap | None:
    if code in (None, "", 0):
        return None
    return (
        LegacyCodeMap.objects.filter(item_type=item_type, code=int(code))
        .select_related("category", "collection")
        .first()
    )


def _map_fields(asset: DigitalAsset, rec: dict) -> None:
    """Legacy record → DigitalAsset fields. Pure mapping, no saves."""
    headline = (
        nz.sentence_case(rec.get("image_headline"))
        or nz.sentence_case(rec.get("image_description"))[:255]
    )
    asset.title = headline[:255] or f"KNA archive image {rec.get('image_refno', '')}"
    asset.description = nz.sentence_case(rec.get("image_description"))
    asset.caption = nz.sentence_case(rec.get("image_caption"))
    asset.asset_type = DigitalAsset.AssetType.PHOTOGRAPH
    asset.photographer = (
        nz.clean_text(rec.get("image_creator"))
        or nz.sentence_case(rec.get("image_creator_jobtitle"))
        or "Staff Photographer"
    )
    asset.photographer_credit = "Kenya News Agency"
    asset.source = nz.clean_text(rec.get("image_source")) or "KNA"
    asset.copyright_holder = "Kenya News Agency"
    asset.publication_date = nz.parse_date(rec.get("image_date_created"))
    asset.capture_date = asset.publication_date

    sub = _resolve(LegacyCodeMap.ItemType.SUB, rec.get("sub_category"))
    main = _resolve(LegacyCodeMap.ItemType.MAIN, rec.get("main_category"))
    asset.category = sub.category if sub else None
    asset.collection = main.collection if main else None

    has_preview = bool(rec.get("image_thumbnails"))
    asset.status = DigitalAsset.Status.PUBLISHED if has_preview else DigitalAsset.Status.DRAFT
    asset.visibility = DigitalAsset.Visibility.PUBLIC


def _map_metadata(asset: DigitalAsset, rec: dict) -> None:
    AssetMetadata.objects.update_or_create(
        asset=asset,
        defaults={
            # Prepend the refno so archive users can search "1398/254"
            "keywords": " ".join(
                filter(
                    None,
                    [
                        nz.clean_text(rec.get("image_refno")),
                        nz.clean_text(rec.get("image_keywords")),
                    ],
                )
            ),
            "location": nz.title_case_location(rec.get("image_scene_location")),
            "county": nz.title_case_location(rec.get("image_county_created")),
            "country": nz.normalize_country(rec.get("image_Iso_country_created")),
            "headline": nz.sentence_case(rec.get("image_headline"))[:255],
            "historical_period": "",
            "language": "en",
        },
    )


def _map_tags(asset: DigitalAsset, rec: dict) -> None:
    names = nz.parse_tags(rec.get("image_keywords"))
    tags = []
    for name in names:
        tag, _ = Tag.objects.get_or_create(
            name=name, defaults={"slug": _unique_slug(Tag, name)[:50]}
        )
        tags.append(tag)
    asset.tags.set(tags)


def _map_variants(asset: DigitalAsset, rec: dict) -> None:
    """
    Thumbnails arrive pre-watermarked from the source. Expected shape once
    they start populating image_thumbnails (align names with their feed):
      [{"size": "small", "url": "...", "mime_type": "image/jpeg", "bytes": 12345}, ...]
    small → 'thumbnail' (listing grids); large → 'preview' (detail page).
    """
    size_to_variant = {"small": "thumbnail", "medium": "preview", "large": "preview"}
    for thumb in rec.get("image_thumbnails") or []:
        variant_name = size_to_variant.get(str(thumb.get("size", "")).lower(), "thumbnail")
        url = thumb.get("url") or thumb.get("path") or ""
        if not url:
            continue
        AssetVariant.objects.update_or_create(
            asset=asset,
            variant_name=variant_name,
            defaults={
                "storage_path": url,
                "mime_type": thumb.get("mime_type", "image/jpeg"),
                "file_size": int(thumb.get("bytes") or 0),
                "checksum": thumb.get("checksum", ""),
            },
        )


def sync_images(records: list[dict]) -> SyncRun:
    run = SyncRun.objects.create(kind=SyncRun.Kind.IMAGES, total=len(records))
    for rec in records:
        try:
            with transaction.atomic():
                result = _sync_one(rec)
            setattr(run, result, getattr(run, result) + 1)
        except Exception as exc:  # noqa: BLE001
            logger.exception("Image sync failed for %s", rec.get("image_id"))
            run.errors.append({"image_id": rec.get("image_id"), "error": str(exc)})
    run.finished_at = timezone.now()
    run.save()
    return run


def _sync_one(rec: dict) -> str:
    """Returns 'created' | 'updated' | 'skipped' | 'conflicts'."""
    external_id = uuid.UUID(rec["image_id"])
    refno = nz.clean_text(rec.get("image_refno"))
    checksum = nz.record_checksum(rec)

    sync = AssetSyncRecord.objects.select_related("asset").filter(external_id=external_id).first()

    if sync is None:
        # asset_number is OURS, derived deterministically from the legacy
        # UUID — refno is NOT unique and sometimes absent, so it can never
        # be a key. It's kept on the sync record purely as provenance
        # metadata (the physical print reference), searchable by archivists.
        asset = DigitalAsset(asset_number=f"KNA-{external_id.hex[:12].upper()}")
        _map_fields(asset, rec)
        asset.save()
        _map_metadata(asset, rec)
        _map_tags(asset, rec)
        _map_variants(asset, rec)
        AssetSyncRecord.objects.create(
            external_id=external_id,
            external_refno=refno,
            asset=asset,
            checksum=checksum,
            payload=rec,
        )
        return "created"

    if sync.checksum == checksum:
        sync.payload = rec  # refresh volatile fields silently
        sync.save(update_fields=["payload", "last_synced_at"])
        return "skipped"

    if sync.sync_locked:
        # Source changed but editors curated this asset locally. Preserve
        # local work; keep the new payload for review; count the conflict.
        sync.payload = rec
        sync.save(update_fields=["payload", "last_synced_at"])
        logger.warning("Sync conflict on locked asset %s (%s)", sync.asset_id, refno)
        return "conflicts"

    asset = sync.asset
    _map_fields(asset, rec)
    asset.save()
    _map_metadata(asset, rec)
    _map_tags(asset, rec)
    _map_variants(asset, rec)
    sync.checksum = checksum
    sync.payload = rec
    sync.external_refno = refno
    sync.save(update_fields=["checksum", "payload", "external_refno", "last_synced_at"])
    return "updated"
