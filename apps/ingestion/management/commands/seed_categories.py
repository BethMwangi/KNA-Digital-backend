"""
Seed and verify the canonical category code map.

The image feed tags every record with numeric codes (main_category "3",
sub_category "9"). This command seeds the official code tables from the
source system so those numbers resolve to real names:

  main categories -> Collections  (1 Political, 2 Economic, 3 Social,
                                   4 Public Service)
  sub-categories  -> Categories   (1 Presidential ... 21 Education)

It then verifies the database against the canonical table: every code
mapped, every name matching (renames are applied), and — with
--verify-assets — every synced asset's payload codes cross-checked
against the category/collection it actually links to.

  python manage.py seed_categories                  # seed/repair + verify map
  python manage.py seed_categories --dry-run        # verify only, write nothing
  python manage.py seed_categories --verify-assets  # also audit synced assets
"""

from django.core.management.base import BaseCommand

from apps.ingestion.models import AssetSyncRecord, LegacyCodeMap
from apps.ingestion.services import sync_categories

# Official code tables from the source system (Photos Main/Sub Categories).
CANONICAL_MAIN = {
    1: "Political",
    2: "Economic",
    3: "Social",
    4: "Public Service",
}
CANONICAL_SUB = {
    1: "Presidential",
    2: "Personality",
    3: "Colonial Affairs",
    4: "Politics",
    5: "Agriculture",
    6: "Ministry",
    7: "Industry",
    8: "Women and Children, Scouts, NGOs and Red Cross",
    9: "Health",
    10: "Culture",
    11: "Sports",
    12: "Transport",
    13: "Accidents",
    14: "Buildings and Monuments",
    15: "Celebrations",
    16: "Security",
    17: "Environment",
    18: "Religion",
    19: "Entertainment",
    20: "Ceremonies",
    21: "Education",
}


def _canonical_records() -> list[dict]:
    recs = [
        {"ItemType": LegacyCodeMap.ItemType.MAIN, "itemCode": code, "ItemDescription": name}
        for code, name in CANONICAL_MAIN.items()
    ]
    recs += [
        {"ItemType": LegacyCodeMap.ItemType.SUB, "itemCode": code, "ItemDescription": name}
        for code, name in CANONICAL_SUB.items()
    ]
    return recs


class Command(BaseCommand):
    help = "Seed the canonical main/sub category code map and verify the database against it."

    def add_arguments(self, parser):
        parser.add_argument("--dry-run", action="store_true", help="Verify only; write nothing.")
        parser.add_argument(
            "--verify-assets",
            action="store_true",
            help="Also cross-check every synced asset's payload codes against its links.",
        )

    # ---------------------------------------------------------------- #
    def handle(self, *args, **options):
        if not options["dry_run"]:
            run = sync_categories(_canonical_records())
            self.stdout.write(
                self.style.SUCCESS(
                    f"Seeded canonical map: {run.created} created, {run.updated} renamed, "
                    f"{run.skipped} already correct, {len(run.errors)} errors"
                )
            )

        self._verify_map()
        if options["verify_assets"]:
            self._verify_assets()

    # ---------------------------------------------------------------- #
    def _verify_map(self):
        self.stdout.write("\n-- Code map vs canonical table --")
        problems = 0
        for item_type, table, kind in (
            (LegacyCodeMap.ItemType.MAIN, CANONICAL_MAIN, "main"),
            (LegacyCodeMap.ItemType.SUB, CANONICAL_SUB, "sub"),
        ):
            for code, name in table.items():
                mapping = (
                    LegacyCodeMap.objects.filter(item_type=item_type, code=code)
                    .select_related("category", "collection")
                    .first()
                )
                if mapping is None:
                    self.stdout.write(self.style.ERROR(f"  MISSING {kind} {code} ({name})"))
                    problems += 1
                    continue
                target = mapping.target
                if target is None:
                    self.stdout.write(
                        self.style.ERROR(f"  UNLINKED {kind} {code} ({name}) — no target row")
                    )
                    problems += 1
                elif target.name != name:
                    self.stdout.write(
                        self.style.WARNING(
                            f"  NAME DRIFT {kind} {code}: ours '{target.name}' vs canonical '{name}'"
                        )
                    )
                    problems += 1
                else:
                    self.stdout.write(f"  ok {kind} {code:>2} -> {target.name}")

        # Codes in our map that the canonical table doesn't know
        known = {(LegacyCodeMap.ItemType.MAIN, c) for c in CANONICAL_MAIN} | {
            (LegacyCodeMap.ItemType.SUB, c) for c in CANONICAL_SUB
        }
        for m in LegacyCodeMap.objects.all():
            if (m.item_type, m.code) not in known:
                self.stdout.write(
                    self.style.WARNING(f"  EXTRA {m.item_type} {m.code} ({m.description})")
                )
                problems += 1

        style = self.style.SUCCESS if problems == 0 else self.style.WARNING
        self.stdout.write(style(f"Map check: {problems} problem(s)."))

    # ---------------------------------------------------------------- #
    def _verify_assets(self):
        self.stdout.write("\n-- Synced assets vs their payload codes --")
        good = fixable = mismatched = 0
        for sync in AssetSyncRecord.objects.select_related(
            "asset__category", "asset__collection"
        ).iterator():
            rec, asset = sync.payload, sync.asset
            expect_sub = CANONICAL_SUB.get(self._int(rec.get("sub_category")))
            expect_main = CANONICAL_MAIN.get(self._int(rec.get("main_category")))
            got_sub = asset.category.name if asset.category else None
            got_main = asset.collection.name if asset.collection else None

            if got_sub == expect_sub and got_main == expect_main:
                good += 1
            elif got_sub is None or got_main is None:
                fixable += 1  # unresolved at sync time; backfill/reseed repairs
            else:
                mismatched += 1
                self.stdout.write(
                    self.style.WARNING(
                        f"  {asset.asset_number}: payload says "
                        f"main={expect_main} sub={expect_sub}, "
                        f"asset has collection={got_main} category={got_sub}"
                    )
                )

        self.stdout.write(
            self.style.SUCCESS(
                f"Assets: {good} correctly tagged, {fixable} missing links "
                f"(run backfill_categories or reseed_assets), {mismatched} mismatched "
                f"(run reseed_assets to re-resolve from payloads)."
            )
        )

    @staticmethod
    def _int(value):
        try:
            return int(value)
        except (TypeError, ValueError):
            return None
