"""
Seed the four usage-purpose licenses buyers choose from at checkout.
Safe to rerun — updates the description if it already exists.

Usage:
    python manage.py seed_licenses
"""

from django.core.management.base import BaseCommand

from apps.commerce.models import License

LICENSES = [
    {
        "name": "Editorial",
        "slug": "editorial",
        "description": "News, journalism and editorial commentary.",
        "allows_commercial": False,
    },
    {
        "name": "Commercial",
        "slug": "commercial",
        "description": "Advertising, marketing and merchandise.",
        "allows_commercial": True,
    },
    {
        "name": "Educational",
        "slug": "educational",
        "description": "Teaching materials, dissertations and public lectures.",
        "allows_commercial": False,
    },
    {
        "name": "Government",
        "slug": "government",
        "description": "Official Government of Kenya publications.",
        "allows_commercial": False,
    },
]


class Command(BaseCommand):
    help = "Seed the Editorial/Commercial/Educational/Government usage licenses."

    def handle(self, *args, **opts):
        created, updated = 0, 0
        for data in LICENSES:
            license_, was_created = License.objects.update_or_create(
                slug=data["slug"],
                defaults={
                    "name": data["name"],
                    "description": data["description"],
                    "allows_commercial": data["allows_commercial"],
                },
            )
            created += was_created
            updated += not was_created

        self.stdout.write(self.style.SUCCESS(f"Licenses: {created} created, {updated} updated."))
