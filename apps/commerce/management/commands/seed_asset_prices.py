"""
Backfill the flat KES price on every asset that doesn't have one yet.
Safe to rerun after new imports — only fills in assets with price=NULL.

Usage:
    python manage.py seed_asset_prices
    python manage.py seed_asset_prices --amount 2000
"""

from django.core.management.base import BaseCommand

from apps.assets.models import DigitalAsset

DEFAULT_AMOUNT = 1500


class Command(BaseCommand):
    help = "Set DigitalAsset.price on every asset that doesn't have one yet."

    def add_arguments(self, parser):
        parser.add_argument(
            "--amount",
            type=int,
            default=DEFAULT_AMOUNT,
            help=f"Price in KES (default: {DEFAULT_AMOUNT}).",
        )

    def handle(self, *args, **opts):
        amount = opts["amount"]
        updated = DigitalAsset.objects.filter(price__isnull=True).update(price=amount)
        self.stdout.write(self.style.SUCCESS(f"Priced {updated} asset(s) at KES {amount}."))
