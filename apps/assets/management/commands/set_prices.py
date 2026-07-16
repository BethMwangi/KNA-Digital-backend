"""
Bulk-assign the flat KES price to digital assets.

Assets import from the archive feed with price=NULL (not purchasable);
this sets prices in bulk. By default only unpriced assets are touched,
so editor-curated prices survive re-runs. The date filters support the
planned old-vs-new pricing split without any schema change.

Examples:
  python manage.py set_prices --price 1500                        # all unpriced
  python manage.py set_prices --price 1500 --dry-run              # count only
  python manage.py set_prices --price 2500 --published-before 1990-01-01
  python manage.py set_prices --price 1000 --published-after 1990-01-01
  python manage.py set_prices --price 1500 --overwrite            # reprice ALL
"""

from datetime import date
from decimal import Decimal, InvalidOperation

from django.core.management.base import BaseCommand, CommandError

from apps.assets.models import DigitalAsset


def _parse_date(value: str) -> date:
    try:
        return date.fromisoformat(value)
    except ValueError as exc:
        raise CommandError(f"Invalid date '{value}' (use YYYY-MM-DD)") from exc


class Command(BaseCommand):
    help = "Bulk-assign the flat price (KES) to assets, optionally filtered by publication date."

    def add_arguments(self, parser):
        parser.add_argument(
            "--price", required=True, help="Flat price in KES, e.g. 1500 or 1500.00"
        )
        parser.add_argument(
            "--published-before", help="Only assets published before this date (YYYY-MM-DD)."
        )
        parser.add_argument(
            "--published-after",
            help="Only assets published on/after this date (YYYY-MM-DD).",
        )
        parser.add_argument(
            "--overwrite",
            action="store_true",
            help="Also reprice assets that already have a price (default: unpriced only).",
        )
        parser.add_argument("--dry-run", action="store_true", help="Report counts without saving.")

    def handle(self, *args, **options):
        try:
            price = Decimal(options["price"])
        except InvalidOperation as exc:
            raise CommandError(f"Invalid price: {options['price']}") from exc
        if price <= 0:
            raise CommandError("Price must be positive.")

        qs = DigitalAsset.objects.all()
        if not options["overwrite"]:
            qs = qs.filter(price__isnull=True)
        if options["published_before"]:
            qs = qs.filter(publication_date__lt=_parse_date(options["published_before"]))
        if options["published_after"]:
            qs = qs.filter(publication_date__gte=_parse_date(options["published_after"]))

        count = qs.count()
        if options["dry_run"]:
            self.stdout.write(self.style.SUCCESS(f"Would set price=KES {price} on {count} assets."))
            return

        updated = qs.update(price=price)
        self.stdout.write(self.style.SUCCESS(f"Set price=KES {price} on {updated} assets."))
        self.stdout.write(
            "Note: cached API responses refresh within API_CACHE_TTL "
            "(or clear now with: python manage.py shell -c "
            '"from django.core.cache import cache; cache.clear()")'
        )
