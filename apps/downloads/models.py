"""
Downloads models — tracks purchased asset downloads (SDD §16.14).

A Download record is created when an Order is paid. The user can then
request a secure, time-limited signed URL to fetch the high-res file.
"""
import hashlib
import time

from django.conf import settings
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
        Generate a time-limited signed URL for a file.

        In production, this would call Supabase Storage or S3 to generate
        a presigned URL. For now it returns a placeholder token-based URL.
        """
        expiry = int(time.time()) + expires_in
        raw = f"{variant.storage_path}:{expiry}:{settings.SECRET_KEY}"
        signature = hashlib.sha256(raw.encode()).hexdigest()[:32]

        # TODO: Replace with real Supabase/S3 presigned URL generation
        return (
            f"/api/v1/downloads/file/{variant.id}/"
            f"?expires={expiry}&sig={signature}"
        )

    def record_download(self):
        """Increment the download counter."""
        self.download_count += 1
        self.save(update_fields=["download_count", "updated_at"])
