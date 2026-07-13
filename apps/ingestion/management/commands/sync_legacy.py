"""
Manual/scheduled ingestion entry point.

Usage:
  python manage.py sync_legacy --categories data/categories.json
  python manage.py sync_legacy --images data/images.json
  python manage.py sync_legacy --categories cats.json --images imgs.json

Same command works today (JSON dumps) and tomorrow (their API): the
Celery task in tasks.py fetches from the API and calls the same services.
"""

import json
from pathlib import Path

from django.core.management.base import BaseCommand, CommandError

from apps.ingestion.services import sync_categories, sync_images


class Command(BaseCommand):
    help = "Ingest legacy KNA archive JSON (categories and/or images)."

    def add_arguments(self, parser):
        parser.add_argument("--categories", type=str, help="Path to categories JSON dump")
        parser.add_argument("--images", type=str, help="Path to images JSON dump")

    def _load(self, path: str) -> list:
        file = Path(path)
        if not file.exists():
            raise CommandError(f"File not found: {path}")
        data = json.loads(file.read_text(encoding="utf-8"))
        if not isinstance(data, list):
            raise CommandError(f"{path} must contain a JSON array")
        return data

    def handle(self, *args, **options):
        if not options["categories"] and not options["images"]:
            raise CommandError("Provide --categories and/or --images")

        # Categories first — image sync resolves codes through the map.
        if options["categories"]:
            run = sync_categories(self._load(options["categories"]))
            self.stdout.write(
                self.style.SUCCESS(
                    f"Categories: {run.created} created, {run.updated} updated, "
                    f"{run.skipped} unchanged, {len(run.errors)} errors"
                )
            )
        if options["images"]:
            run = sync_images(self._load(options["images"]))
            self.stdout.write(
                self.style.SUCCESS(
                    f"Images: {run.created} created, {run.updated} updated, "
                    f"{run.skipped} unchanged, {run.conflicts} conflicts, "
                    f"{len(run.errors)} errors"
                )
            )
            if run.errors:
                self.stdout.write(self.style.WARNING(f"First error: {run.errors[0]}"))
