"""
Downloads models — tracks purchased asset downloads (SDD §16.14).

A Download record is created when an Order is paid. The user can then
request a secure, time-limited signed URL to fetch the high-res file.
"""

from django.conf import settings
from django.core.files.storage import storages
from django.db import models
from django.utils.translation import gettext_lazy as _

from apps.assets.models import AssetVariant, DigitalAsset
from apps.commerce.models import License, Order
from core.models import BaseModel


class Download(BaseModel):
    """
    Represents a user's right to download a purchased asset.
    Created automatically when an order is marked as paid.
    """

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name="downloads",
    )
    order = models.ForeignKey(
        Order,
        on_delete=models.PROTECT,
        related_name="downloads",
    )
    asset = models.ForeignKey(
        DigitalAsset,
        on_delete=models.PROTECT,
        related_name="downloads",
    )
    license = models.ForeignKey(
        License,
        on_delete=models.PROTECT,
        related_name="downloads",
    )
    download_count = models.PositiveIntegerField(default=0)
    max_downloads = models.PositiveIntegerField(
        default=5,
        help_text=_("Maximum number of times this file can be downloaded."),
    )

    class Meta:
        db_table = "downloads"
        unique_together = ["user", "asset", "license"]
        ordering = ["-created_at"]

    def __str__(self):
        return f"Download: {self.asset.title} by {self.user.email}"

    @property
    def downloads_remaining(self):
        return max(0, self.max_downloads - self.download_count)

    @property
    def can_download(self):
        return self.download_count < self.max_downloads

    def generate_signed_url(self, variant: AssetVariant, expires_in: int = 3600) -> str:
        """
        Time-limited signed URL for the purchased file, via the
        "private_media" storage alias — a real presigned Supabase/S3 URL in
        production, a plain local-disk URL in dev (see core/storage.py vs
        core/storage_s3.py — only the S3 backend supports `expire`).
        """
        storage = storages["private_media"]
        if hasattr(storage, "querystring_expire"):
            return storage.url(variant.storage_path, expire=expires_in)
        return storage.url(variant.storage_path)

    def record_download(self):
        """Increment the download counter."""
        self.download_count += 1
        self.save(update_fields=["download_count", "updated_at"])
