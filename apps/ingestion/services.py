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
import re
import uuid

from django.conf import settings
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
ASSET_NUMBER_PATTERN = r"^KNA-\d{6}$"


def next_asset_number() -> str:
    """Next e-commerce style SKU: KNA-000001, KNA-000002, ...
    Zero-padded so string ordering IS numeric ordering. Sync runs are
    single-threaded, so a max-scan is race-safe enough here."""
    last = (
        DigitalAsset.all_objects.filter(asset_number__regex=ASSET_NUMBER_PATTERN)
        .order_by("-asset_number")
        .values_list("asset_number", flat=True)
        .first()
    )
    nxt = int(last.rsplit("-", 1)[1]) + 1 if last else 1
    return f"KNA-{nxt:06d}"


def _resolve(item_type: str, code) -> LegacyCodeMap | None:
    """Codes arrive as ints (JSON dumps) or strings ('3', live feed)."""
    if code in (None, "", 0):
        return None
    try:
        code = int(code)
    except (TypeError, ValueError):
        return None
    return (
        LegacyCodeMap.objects.filter(item_type=item_type, code=code)
        .select_related("category", "collection")
        .first()
    )


def _map_fields(asset: DigitalAsset, rec: dict) -> None:
    """Legacy record → DigitalAsset fields. Pure mapping, no saves."""
    # Title IS the source's image description (it's what the site shows
    # under each photo); headline and refno are fallbacks only.
    description = nz.sentence_case(rec.get("image_description"))
    asset.title = (
        description[:255]
        or nz.sentence_case(rec.get("image_headline"))[:255]
        or f"KNA archive image {rec.get('image_refno', '')}"
    )
    asset.description = description
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

    # Live feed sends "thumbnails", the JSON dumps sent "image_thumbnails" —
    # the parser understands both, so use it as the single source of truth.
    has_preview = bool(_parse_thumbnail_entries(rec))
    asset.status = DigitalAsset.Status.PUBLISHED if has_preview else DigitalAsset.Status.DRAFT
    asset.visibility = DigitalAsset.Visibility.PUBLIC

    # Flat launch price so seeded assets are purchasable immediately.
    # Only fills the gap — editor-set prices are never overwritten
    # (use set_prices for bulk repricing / the old-vs-new split later).
    if asset.price is None:
        asset.price = settings.ASSET_DEFAULT_PRICE


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
    # Date tags — year and decade ("1979", "1970s") make era search work.
    pub = nz.parse_date(rec.get("image_date_created"))
    if pub:
        names += [str(pub.year), f"{pub.year // 10 * 10}s"]
    tags = []
    for name in names:
        tag, _ = Tag.objects.get_or_create(
            name=name, defaults={"slug": _unique_slug(Tag, name)[:50]}
        )
        tags.append(tag)
    asset.tags.set(tags)


def _parse_thumbnail_entries(rec: dict) -> dict:
    """
    Normalise both feed shapes into {variant_name: url}:

    Live Urithi feed — URL strings encode size AND side in the filename:
        ".../13ea66...-600_1.jpeg"   -> 600px  front -> 'thumbnail' (grid)
        ".../13ea66...-1200_1.jpeg"  -> 1200px front -> 'preview'  (detail)
        ".../13ea66...-600_2.jpeg"   -> 600px  back  -> 'thumbnail_back'
        ".../13ea66...-1200_2.jpeg"  -> 1200px back  -> 'preview_back'
    Side 2 is the BACK of the physical print (stamps, handwritten
    captions) — exposed so buyers see they're getting front AND back.
    A 2-entry list is a front-only print; 4 entries means both sides.

    Dict shape (earlier spec) — [{"size": "small", "url": ...}] still works.
    """
    entries = rec.get("thumbnails") or rec.get("image_thumbnails") or []
    size_to_variant = {"small": "thumbnail", "medium": "preview", "large": "preview"}
    out: dict[str, str] = {}
    for item in entries:
        if isinstance(item, dict):
            url = item.get("url") or item.get("path") or ""
            variant = size_to_variant.get(str(item.get("size", "")).lower(), "thumbnail")
        else:
            url = str(item).strip()
            m = re.search(r"-(\d{3,4})_(\d+)\.(?:jpe?g|png)$", url, re.IGNORECASE)
            px = int(m.group(1)) if m else 0
            side = int(m.group(2)) if m else 1
            variant = "thumbnail" if 0 < px <= 800 else "preview"
            if side >= 2:
                variant += "_back"
        if url and variant not in out:
            out[variant] = url
    return out


def _map_variants(asset: DigitalAsset, rec: dict) -> None:
    """Source thumbnails -> AssetVariant rows stored in OUR bucket.
    Mirror-first: files are downloaded and saved during sync, so the
    storefront never links the source server. A failed download raises,
    the record's transaction rolls back, it is NOT acked, and the feed
    re-delivers it on a later run.
    MIRROR_THUMBNAILS=False (emergency fallback only) stores the source
    URL directly instead of downloading."""
    from .mirroring import fetch_and_store

    for variant_name, url in _parse_thumbnail_entries(rec).items():
        if settings.MIRROR_THUMBNAILS:
            values = fetch_and_store(
                url, asset_number=asset.asset_number, variant_name=variant_name
            )
        else:
            values = {"storage_path": url, "mime_type": "image/jpeg", "file_size": 0}
        AssetVariant.objects.update_or_create(
            asset=asset, variant_name=variant_name, defaults=values
        )


def sync_images(records: list[dict]) -> SyncRun:
    run = SyncRun.objects.create(kind=SyncRun.Kind.IMAGES, total=len(records))
    for rec in records:
        try:
            with transaction.atomic():
                result, _ = _sync_one(rec)
            setattr(run, result, getattr(run, result) + 1)
        except Exception as exc:  # noqa: BLE001
            logger.exception("Image sync failed for %s", rec.get("image_id"))
            run.errors.append({"image_id": rec.get("image_id"), "error": str(exc)})
    run.finished_at = timezone.now()
    run.save()
    return run


def _sync_one(rec: dict) -> tuple[str, AssetSyncRecord]:
    """Returns ('created' | 'updated' | 'skipped' | 'conflicts', sync record).
    The sync record's id doubles as the ack response_id for the live feed."""
    external_id = uuid.UUID(rec["image_id"])
    refno = nz.clean_text(rec.get("image_refno"))
    checksum = nz.record_checksum(rec)

    sync = AssetSyncRecord.objects.select_related("asset").filter(external_id=external_id).first()

    if sync is None:
        # asset_number is OUR e-commerce SKU (KNA-000001...), independent
        # of the source's image_id — identity/dedupe lives on the sync
        # record's external_id, and the physical print refno is kept there
        # too as provenance metadata, searchable by archivists.
        asset = DigitalAsset(asset_number=next_asset_number())
        _map_fields(asset, rec)
        asset.save()
        _map_metadata(asset, rec)
        _map_tags(asset, rec)
        _map_variants(asset, rec)
        sync = AssetSyncRecord.objects.create(
            external_id=external_id,
            external_refno=refno,
            asset=asset,
            checksum=checksum,
            payload=rec,
        )
        return "created", sync

    if sync.checksum == checksum:
        sync.payload = rec  # refresh volatile fields silently
        sync.save(update_fields=["payload", "last_synced_at"])
        return "skipped", sync

    if sync.sync_locked:
        # Source changed but editors curated this asset locally. Preserve
        # local work; keep the new payload for review; count the conflict.
        sync.payload = rec
        sync.save(update_fields=["payload", "last_synced_at"])
        logger.warning("Sync conflict on locked asset %s (%s)", sync.asset_id, refno)
        return "conflicts", sync

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
    return "updated", sync


# --------------------------------------------------------------------- #
# Live Urithi feed — pull loop with ack protocol
# --------------------------------------------------------------------- #
def pull_urithi_batches(max_batches: int | None = None) -> SyncRun:
    """
    Drain the live feed: fetch a batch (~10 records) -> store each record
    in its own transaction -> ack ONLY after that commit -> the server
    unlocks the next batch -> repeat until an empty batch.

    Safety properties:
    - ack-after-commit: a crash between store and ack just causes
      re-delivery, and the checksum makes re-delivery a harmless skip.
    - response_id is OUR AssetSyncRecord.id, so their logs trace back
      to our row.
    - zero-progress guard: if nothing in a batch could be acked, stop —
      otherwise a poison batch would be re-fetched forever.
    - max_batches caps a single run (smoke tests, cron slices).
    """
    from .urithi_client import UrithiClient, UrithiError

    client = UrithiClient()
    run = SyncRun.objects.create(kind=SyncRun.Kind.IMAGES)
    batches = 0
    while max_batches is None or batches < max_batches:
        try:
            batch = client.fetch_batch()
        except UrithiError as exc:
            logger.error("Urithi fetch failed: %s", exc)
            run.errors.append({"error": str(exc)})
            break
        if not batch:
            logger.info("Feed is empty — caught up after %d batch(es).", batches)
            break  # caught up
        batches += 1
        run.total += len(batch)
        logger.info("=== Batch %d: %d records ===", batches, len(batch))

        acked = 0
        for rec in batch:
            image_id = str(rec.get("image_id") or "")
            refno = rec.get("image_refno", "")
            try:
                with transaction.atomic():
                    result, sync = _sync_one(rec)
                setattr(run, result, getattr(run, result) + 1)
                logger.info(
                    "%s image_id=%s refno=%s -> asset %s",
                    result.upper(),
                    image_id,
                    refno,
                    sync.asset.asset_number,
                )
            except Exception as exc:  # noqa: BLE001
                logger.exception("FAILED image_id=%s refno=%s", image_id, refno)
                run.errors.append({"image_id": image_id, "error": str(exc)})
                continue  # not stored -> NOT acked -> they resend it

            try:
                client.ack(image_id, str(sync.id))
                acked += 1
            except UrithiError as exc:
                # Stored but not acked: they resend, the checksum skips it,
                # and the ack succeeds on that retry. Safe — just visible.
                logger.warning("%s", exc)
                run.errors.append({"image_id": image_id, "error": str(exc)})

        logger.info(
            "Batch %d done: %d/%d acked | run totals: +%d ~%d =%d !%d err=%d",
            batches,
            acked,
            len(batch),
            run.created,
            run.updated,
            run.skipped,
            run.conflicts,
            len(run.errors),
        )
        if acked == 0:
            logger.warning(
                "Urithi pull: no record in this batch could be stored+acked — "
                "stopping so the same batch isn't re-fetched forever."
            )
            break

    run.finished_at = timezone.now()
    run.save()
    return run
