"""
Repair uncategorized synced assets.

If an image record arrives before its category code exists in
LegacyCodeMap (or a brand-new code appears in the feed), the asset
imports with category/collection = NULL. After re-syncing categories
(sync_legacy --categories ...), run this to re-resolve those assets
from the raw payload kept on their AssetSyncRecord.

  python manage.py backfill_categories            # apply
  python manage.py backfill_categories --dry-run  # report only
"""

from django.core.management.base import BaseCommand
from django.db.models import Q

from apps.ingestion.models import AssetSyncRecord, LegacyCodeMap
from apps.ingestion.services import _resolve


class Command(BaseCommand):
    help = "Re-resolve category/collection for synced assets that imported uncategorized."

    def add_arguments(self, parser):
        parser.add_argument("--dry-run", action="store_true", help="Report without saving.")

    def handle(self, *args, **options):
        candidates = (
            AssetSyncRecord.objects.select_related("asset")
            .filter(sync_locked=False)
            .filter(Q(asset__category__isnull=True) | Q(asset__collection__isnull=True))
        )
        fixed, unresolved = 0, 0
        for sync in candidates.iterator():
            asset, rec = sync.asset, sync.payload
            update_fields = []
            if asset.category_id is None:
                sub = _resolve(LegacyCodeMap.ItemType.SUB, rec.get("sub_category"))
                if sub and sub.category:
                    asset.category = sub.category
                    update_fields.append("category")
            if asset.collection_id is None:
                main = _resolve(LegacyCodeMap.ItemType.MAIN, rec.get("main_category"))
                if main and main.collection:
                    asset.collection = main.collection
                    update_fields.append("collection")
            if update_fields:
                fixed += 1
                if not options["dry_run"]:
                    asset.save(update_fields=update_fields + ["updated_at"])
            else:
                unresolved += 1
        verb = "Would fix" if options["dry_run"] else "Fixed"
        self.stdout.write(
            self.style.SUCCESS(
                f"{verb} {fixed} assets; {unresolved} still lack a mapped code "
                f"(re-sync categories, then re-run)."
            )
        )
