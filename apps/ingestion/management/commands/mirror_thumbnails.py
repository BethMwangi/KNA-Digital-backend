"""
Repair assets that still link the source server.

Policy is mirror-first: sync now stores thumbnail files in OUR bucket
before a record is ever acked. But rows synced before this policy hold
external URLs in AssetVariant.storage_path, and re-pulling won't fix
them (unchanged checksums are skipped). This command downloads those
files into our public bucket and repoints the rows, so nothing on the
storefront depends on the source server.

  python manage.py mirror_thumbnails             # repair all hotlinked
  python manage.py mirror_thumbnails --dry-run   # count only
  python manage.py mirror_thumbnails --limit 20  # smoke test first
"""

from django.core.management.base import BaseCommand

from apps.assets.models import AssetVariant
from apps.ingestion.mirroring import mirror_variant


class Command(BaseCommand):
    help = "Move hotlinked (external-URL) variant thumbnails into our public bucket."

    def add_arguments(self, parser):
        parser.add_argument("--limit", type=int, default=None, help="Max variants this run.")
        parser.add_argument("--dry-run", action="store_true", help="Report without mirroring.")

    def handle(self, *args, **options):
        qs = AssetVariant.objects.filter(storage_path__startswith="http").order_by("created_at")
        total = qs.count()
        if options["dry_run"]:
            self.stdout.write(self.style.SUCCESS(f"{total} variants still hotlinked."))
            return
        if options["limit"]:
            qs = qs[: options["limit"]]

        mirrored = failed = 0
        for variant in qs.iterator():
            if mirror_variant(str(variant.id)):
                mirrored += 1
            else:
                failed += 1  # details in the log; row untouched, re-run to retry
            if (mirrored + failed) % 25 == 0:
                self.stdout.write(f"  ... {mirrored + failed} of {total} processed")

        self.stdout.write(
            self.style.SUCCESS(
                f"Mirrored {mirrored} of {total} hotlinked variants; {failed} failed."
            )
        )
        if failed:
            self.stdout.write(
                self.style.WARNING("Check the log output above; re-run to retry failures.")
            )
        if mirrored:
            self.stdout.write(
                "Clear cached API responses to serve the new URLs immediately:\n"
                '  python manage.py shell -c "from django.core.cache import cache; cache.clear()"'
            )
