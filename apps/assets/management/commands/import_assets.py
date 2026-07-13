import json
import os
from datetime import datetime

from django.conf import settings
from django.core.management.base import BaseCommand
from django.db import transaction

from apps.assets.models import AssetMetadata, DigitalAsset


class Command(BaseCommand):
    help = "Imports digital assets and metadata from ImageTextFiles.json"

    def handle(self, *args, **options):
        base_dir = settings.BASE_DIR
        assets_path = os.path.join(base_dir, "SampleJsonFiles", "ImageTextFiles.json")

        if not os.path.exists(assets_path):
            self.stdout.write(self.style.ERROR(f"File not found: {assets_path}"))
            return

        with open(assets_path, "r", encoding="utf-8") as f:
            data = json.load(f)

        self.stdout.write(f"Found {len(data)} assets to import...")

        success_count = 0
        error_count = 0

        with transaction.atomic():
            for item in data:
                try:
                    # Parse dates
                    capture_date = None
                    if item.get("image_date_created"):
                        try:
                            capture_date = datetime.strptime(
                                item["image_date_created"], "%Y-%m-%d"
                            ).date()
                        except ValueError:
                            pass

                    # Create or update DigitalAsset
                    asset, created = DigitalAsset.objects.update_or_create(
                        asset_number=item.get("image_refno"),
                        defaults={
                            "title": item.get("image_headline") or "Untitled",
                            "description": item.get("image_description") or "",
                            "caption": item.get("image_caption") or "",
                            "asset_type": DigitalAsset.AssetType.PHOTOGRAPH,
                            "status": DigitalAsset.Status.PUBLISHED,
                            "visibility": DigitalAsset.Visibility.PUBLIC,
                            "source": item.get("image_source") or "",
                            "photographer": item.get("image_creator") or "",
                            "capture_date": capture_date,
                        },
                    )

                    # Create or update AssetMetadata
                    metadata, meta_created = AssetMetadata.objects.update_or_create(
                        asset=asset,
                        defaults={
                            "legacy_image_id": item.get("image_id"),
                            "headline": item.get("image_headline") or "",
                            "keywords": item.get("image_keywords") or "",
                            "location": item.get("image_scene_location") or "",
                            "country": item.get("image_Iso_country_created") or "Kenya",
                            "county": item.get("image_county_created") or "",
                            "intellectual_genre": item.get("intellectual_genre") or "",
                            "iptc_scene": item.get("iptc_scene") or "",
                            "image_source_type": item.get("image_source_type") or "",
                            "image_logos": item.get("image_logos") or "",
                            "creator_job_title": item.get("image_creator_jobtitle") or "",
                            "image_dimensions": item.get("image_dimensions") or "",
                            "image_remarks": item.get("image_remarks") or "",
                            "main_category_code": item.get("main_category"),
                            "sub_category_code": item.get("sub_category"),
                            "thumbnails": item.get("image_thumbnails") or [],
                        },
                    )

                    success_count += 1
                except Exception as e:
                    self.stdout.write(
                        self.style.ERROR(
                            f"Failed to import asset {item.get('image_refno')}: {str(e)}"
                        )
                    )
                    error_count += 1

        self.stdout.write(
            self.style.SUCCESS(
                f"Import complete! Successfully imported: {success_count}. Errors: {error_count}."
            )
        )
