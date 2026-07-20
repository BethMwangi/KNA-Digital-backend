"""
One-time (and safe to re-run) backfill of DigitalAsset.search_vector for
rows that predate the search feature, or after changing what feeds the
vector in apps/assets/search.py::build_search_vector.

New/re-synced assets keep themselves in sync automatically via the
ingestion pipeline — this command is only for catching up existing rows.

  python manage.py backfill_search_vectors
"""

from django.core.management.base import BaseCommand

from apps.assets.models import DigitalAsset
from apps.assets.search import build_search_vector


class Command(BaseCommand):
    help = "Backfill DigitalAsset.search_vector for all assets (single bulk UPDATE)."

    def handle(self, *args, **options):
        total = DigitalAsset.objects.count()
        updated = DigitalAsset.objects.update(search_vector=build_search_vector())
        self.stdout.write(
            self.style.SUCCESS(f"search_vector backfilled for {updated} of {total} assets.")
        )
