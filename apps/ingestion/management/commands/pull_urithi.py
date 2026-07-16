"""
Pull the live Urithi feed: fetch batch -> store -> ack -> next batch.

Usage:
  python manage.py pull_urithi              # drain the feed
  python manage.py pull_urithi --batches 2  # smoke test (~20 records)

Sequencing note: categories must already be synced (sync_legacy
--categories ...) so main/sub codes resolve through LegacyCodeMap.
Records with unknown codes land uncategorized; repair them later with
backfill_categories after re-syncing categories.
"""

from django.core.management.base import BaseCommand

from apps.ingestion.services import pull_urithi_batches


class Command(BaseCommand):
    help = "Pull image records from the live Urithi feed (ack-after-commit protocol)."

    def add_arguments(self, parser):
        parser.add_argument(
            "--batches",
            type=int,
            default=None,
            help="Max batches this run (~10 records each). Default: run until the feed is empty.",
        )

    def handle(self, *args, **options):
        run = pull_urithi_batches(max_batches=options["batches"])
        self.stdout.write(
            self.style.SUCCESS(
                f"Pulled {run.total}: {run.created} created, {run.updated} updated, "
                f"{run.skipped} unchanged, {run.conflicts} conflicts, "
                f"{len(run.errors)} errors"
            )
        )
        if run.errors:
            self.stdout.write(self.style.WARNING(f"First error: {run.errors[0]}"))
