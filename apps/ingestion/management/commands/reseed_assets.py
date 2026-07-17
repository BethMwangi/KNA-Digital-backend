"""
Rebuild the asset catalogue from the raw payloads kept on AssetSyncRecord.

Why this exists: the feed only sends UNACKNOWLEDGED records, so already-
acked images can never be re-pulled — but we stored every record verbatim
in AssetSyncRecord.payload. This command re-runs the current mapping
(title = image description, default price, category resolution, thumbnail
mirror into OUR bucket) over those payloads. Run it whenever the mapping
rules change.

It also deletes junk: assets WITHOUT a sync record (old TIFF/test imports
with filename titles). Categories, collections and sync records stay.

  python manage.py reseed_assets --dry-run       # counts only
  python manage.py reseed_assets --limit 5       # smoke test the remap
  python manage.py reseed_assets                 # full run
  python manage.py reseed_assets --keep-unsynced # remap only, delete nothing
"""

import logging

from django.core.management.base import BaseCommand
from django.db import transaction
from django.db.models import ProtectedError

from apps.assets.models import DigitalAsset
from apps.ingestion.models import AssetSyncRecord
from apps.ingestion.services import (
    _map_fields,
    _map_metadata,
    _map_tags,
    _map_variants,
    next_asset_number,
)

logger = logging.getLogger(__name__)


class Command(BaseCommand):
    help = "Delete non-feed junk assets and rebuild feed assets from stored payloads."

    def add_arguments(self, parser):
        parser.add_argument("--limit", type=int, default=None, help="Max records to remap.")
        parser.add_argument("--dry-run", action="store_true", help="Report counts only.")
        parser.add_argument(
            "--keep-unsynced",
            action="store_true",
            help="Skip deleting assets that lack a sync record (TIFF/test imports).",
        )
        parser.add_argument(
            "--recreate",
            action="store_true",
            help="Full clean reload: build each feed asset as a BRAND-NEW row "
            "(fresh id + fresh sequential KNA-###### number), relink the sync "
            "record, delete the old row. Old asset ids/URLs stop existing.",
        )

    def handle(self, *args, **options):
        junk = DigitalAsset.all_objects.filter(sync_record__isnull=True)
        records = AssetSyncRecord.objects.select_related("asset").order_by("created_at")

        if options["dry_run"]:
            self.stdout.write(
                self.style.SUCCESS(
                    f"Would delete {junk.count()} non-feed assets and remap "
                    f"{records.count()} feed assets from stored payloads "
                    f"({records.filter(sync_locked=True).count()} locked will be skipped)."
                )
            )
            return

        # 1. Junk: assets that never came from the feed (no payload to
        #    rebuild from). Their bucket files can be removed in the
        #    dashboard; DB rows go now.
        if not options["keep_unsynced"]:
            try:
                deleted, per_model = junk.delete()
                self.stdout.write(
                    self.style.SUCCESS(f"Deleted {deleted} non-feed rows: {per_model}")
                )
            except ProtectedError as exc:
                self.stdout.write(
                    self.style.ERROR(
                        f"Some assets are referenced by orders/downloads and were kept: {exc}"
                    )
                )

        # 2. Remap every feed asset from its stored payload with the
        #    CURRENT mapping rules. Thumbnails are re-downloaded into our
        #    bucket (same paths, overwritten) — mirror-first, per record.
        if options["limit"]:
            records = records[: options["limit"]]

        remapped = skipped = failed = 0
        for sync in records.iterator():
            if sync.sync_locked:
                skipped += 1
                continue
            try:
                with transaction.atomic():
                    rec = sync.payload
                    if options["recreate"]:
                        # New row first, relink sync, THEN delete the old
                        # row — deleting first would cascade the sync
                        # record and lose the payload forever.
                        old = sync.asset
                        asset = DigitalAsset(asset_number=next_asset_number())
                        _map_fields(asset, rec)
                        asset.save()
                        _map_metadata(asset, rec)
                        _map_tags(asset, rec)
                        _map_variants(asset, rec)
                        sync.asset = asset
                        sync.save(update_fields=["asset", "last_synced_at"])
                        old.delete(hard=True)
                    else:
                        asset = sync.asset
                        _map_fields(asset, rec)
                        asset.save()
                        _map_metadata(asset, rec)
                        _map_tags(asset, rec)
                        _map_variants(asset, rec)
                remapped += 1
                logger.info("REMAPPED %s -> %.60s", asset.asset_number, asset.title)
            except Exception as exc:  # noqa: BLE001
                failed += 1
                logger.exception("Remap failed for %s: %s", sync.external_id, exc)
            if (remapped + failed) % 25 == 0:
                self.stdout.write(f"  ... {remapped + failed} processed")

        self.stdout.write(
            self.style.SUCCESS(
                f"Remapped {remapped} assets from payloads; {skipped} locked skipped; "
                f"{failed} failed (see log; re-run to retry)."
            )
        )
        if remapped:
            self.stdout.write(
                "Clear cached API responses to serve the changes immediately:\n"
                '  python manage.py shell -c "from django.core.cache import cache; cache.clear()"'
            )
