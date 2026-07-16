"""
Assign a random publication_date to every asset that doesn't have one yet —
so demo/legacy-imported records (which carry no real capture date) don't
all show up as null, and the "latest" endpoint has something to sort by.

Usage:
    python manage.py backfill_publication_dates
    python manage.py backfill_publication_dates --start 1960-01-01 --end 2015-12-31
"""

import random
from datetime import date, timedelta

from django.core.management.base import BaseCommand, CommandError

from apps.assets.models import DigitalAsset

DEFAULT_START = date(1960, 1, 1)
DEFAULT_END = date(2015, 12, 31)


class Command(BaseCommand):
    help = "Backfill a random publication_date onto every asset missing one."

    def add_arguments(self, parser):
        parser.add_argument("--start", type=str, default=None, help="YYYY-MM-DD")
        parser.add_argument("--end", type=str, default=None, help="YYYY-MM-DD")

    def handle(self, *args, **opts):
        start = self._parse(opts["start"], DEFAULT_START)
        end = self._parse(opts["end"], DEFAULT_END)
        if start >= end:
            raise CommandError("--start must be before --end")

        span_days = (end - start).days
        updated = 0
        for asset in DigitalAsset.objects.filter(publication_date__isnull=True):
            asset.publication_date = start + timedelta(days=random.randint(0, span_days))
            asset.save(update_fields=["publication_date", "updated_at"])
            updated += 1

        self.stdout.write(self.style.SUCCESS(f"Backfilled publication_date on {updated} asset(s)."))

    def _parse(self, value, default):
        if not value:
            return default
        try:
            return date.fromisoformat(value)
        except ValueError as exc:
            raise CommandError(f"Invalid date: {value!r} (expected YYYY-MM-DD)") from exc
