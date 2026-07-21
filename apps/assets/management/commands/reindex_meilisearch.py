"""
Full rebuild of the Meilisearch index from Postgres (the source of
truth never changes, so this is always safe to re-run).

Needed:
  - Once after first deploying Meilisearch, to backfill existing assets.
  - After any bulk data change (reseed_assets, backfill_categories, etc.)
  - On every boot, if Meilisearch runs on a host with no persistent disk
    (e.g. a free-tier Render service) — its data is wiped on restart, so
    treat the index as a rebuildable cache and repopulate it at startup.

  python manage.py reindex_meilisearch
"""

from django.core.management.base import BaseCommand

from apps.assets.meilisearch_client import reindex_all


class Command(BaseCommand):
    help = "Rebuild the Meilisearch search index from Postgres (published+public assets only)."

    def handle(self, *args, **options):
        count = reindex_all()
        if count:
            self.stdout.write(self.style.SUCCESS(f"Indexed {count} assets into Meilisearch."))
        else:
            self.stdout.write(
                self.style.WARNING(
                    "Indexed 0 assets — either there are none to index, or Meilisearch is "
                    "not configured/reachable (check MEILISEARCH_URL). Search will keep "
                    "working via the Postgres fallback either way."
                )
            )
