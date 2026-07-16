"""
Ingestion models — ADDITIVE ONLY. Your existing assets tables are untouched;
these three tables sit alongside them and hold everything the sync needs.

AssetSyncRecord  — identity bridge: legacy image_id ↔ our DigitalAsset,
                   change-detection checksum, and the raw payload so no
                   source field is ever lost even if we don't map it yet.
LegacyCodeMap    — resolves legacy (item_type, code) pairs to our
                   Category (subcategories) or Collection (main categories).
SyncRun          — observability: what happened on each run.
"""

from django.db import models

from apps.assets.models import Category, Collection, DigitalAsset
from core.models import BaseModel


class LegacyCodeMap(BaseModel):
    class ItemType(models.TextChoices):
        MAIN = "PHTMainCategory", "Main category → Collection"
        SUB = "PHTSubCategory", "Subcategory → Category"

    item_type = models.CharField(max_length=30, choices=ItemType.choices)
    code = models.IntegerField()
    description = models.CharField(max_length=200)
    category = models.ForeignKey(
        Category, null=True, blank=True, on_delete=models.SET_NULL, related_name="legacy_codes"
    )
    collection = models.ForeignKey(
        Collection, null=True, blank=True, on_delete=models.SET_NULL, related_name="legacy_codes"
    )

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=["item_type", "code"], name="uniq_legacy_code")
        ]
        indexes = [models.Index(fields=["item_type", "code"])]

    def __str__(self):
        return f"{self.item_type}:{self.code} → {self.description}"

    @property
    def target(self):
        return self.collection if self.item_type == self.ItemType.MAIN else self.category


class AssetSyncRecord(BaseModel):
    """One row per legacy image. The contract with the source system."""

    external_id = models.UUIDField(
        unique=True, db_index=True, help_text="Legacy image_id — the dedupe key"
    )
    external_refno = models.CharField(
        max_length=50,
        blank=True,
        db_index=True,
        help_text="Legacy image_refno (e.g. 305/120) — physical "
        "print reference. NOT unique, may be absent; "
        "provenance metadata only, never an identity key.",
    )
    asset = models.OneToOneField(DigitalAsset, on_delete=models.CASCADE, related_name="sync_record")
    checksum = models.CharField(
        max_length=64,
        help_text="SHA-256 of the normalised source record; "
        "unchanged checksum → skip on re-sync",
    )
    payload = models.JSONField(
        default=dict,
        help_text="Raw legacy record, verbatim. Unmapped fields "
        "(iptc_scene, genre, dimensions…) live here.",
    )
    last_synced_at = models.DateTimeField(auto_now=True)
    sync_locked = models.BooleanField(
        default=False,
        help_text="Set by editors after curating an asset locally. Locked assets "
        "are never overwritten by sync; conflicts are logged instead.",
    )

    class Meta:
        indexes = [models.Index(fields=["external_refno"])]

    def __str__(self):
        return f"{self.external_refno} ({self.external_id})"


class SyncRun(BaseModel):
    class Kind(models.TextChoices):
        CATEGORIES = "categories"
        IMAGES = "images"

    kind = models.CharField(max_length=20, choices=Kind.choices)
    started_at = models.DateTimeField(auto_now_add=True)
    finished_at = models.DateTimeField(null=True, blank=True)
    total = models.IntegerField(default=0)
    created = models.IntegerField(default=0)
    updated = models.IntegerField(default=0)
    skipped = models.IntegerField(default=0)
    conflicts = models.IntegerField(default=0)
    errors = models.JSONField(default=list, blank=True)

    def __str__(self):
        return f"{self.kind} run {self.started_at:%Y-%m-%d %H:%M} (+{self.created} ~{self.updated})"
