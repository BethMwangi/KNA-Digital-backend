from django.db import models
from django.utils.translation import gettext_lazy as _
from core.models import BaseModel

class Category(BaseModel):
    name = models.CharField(max_length=100, unique=True)
    slug = models.SlugField(max_length=100, unique=True)
    code = models.CharField(
        max_length=10,
        blank=True,
        help_text=_("KNA category code, e.g. '1', '10'."),
    )
    description = models.TextField(blank=True)
    parent = models.ForeignKey(
        "self",
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name="subcategories",
        help_text=_("Parent category. NULL for top-level main categories."),
    )

    class Meta:
        verbose_name_plural = "Categories"

    def __str__(self):
        if self.parent:
            return f"{self.parent.name} → {self.name}"
        return self.name

class Collection(BaseModel):
    name = models.CharField(max_length=100, unique=True)
    slug = models.SlugField(max_length=100, unique=True)
    description = models.TextField(blank=True)

    def __str__(self):
        return self.name

class Tag(BaseModel):
    name = models.CharField(max_length=50, unique=True)
    slug = models.SlugField(max_length=50, unique=True)

    def __str__(self):
        return self.name

class DigitalAsset(BaseModel):
    class AssetType(models.TextChoices):
        PHOTOGRAPH = "photograph", _("Photograph")
        VIDEO = "video", _("Video")
        AUDIO = "audio", _("Audio")
        PDF = "pdf", _("PDF")
        NEWSPAPER = "newspaper", _("Newspaper")
        DOCUMENT = "document", _("Document")

    class Status(models.TextChoices):
        DRAFT = "draft", _("Draft")
        REVIEW = "review", _("Review")
        PUBLISHED = "published", _("Published")
        ARCHIVED = "archived", _("Archived")

    class Visibility(models.TextChoices):
        PUBLIC = "public", _("Public")
        PRIVATE = "private", _("Private")
        RESTRICTED = "restricted", _("Restricted")

    asset_number = models.CharField(max_length=50, unique=True, db_index=True)
    title = models.CharField(max_length=255, db_index=True)
    description = models.TextField(blank=True)
    caption = models.TextField(blank=True)
    asset_type = models.CharField(max_length=50, choices=AssetType.choices, default=AssetType.PHOTOGRAPH)
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.DRAFT, db_index=True)
    visibility = models.CharField(max_length=20, choices=Visibility.choices, default=Visibility.PRIVATE)
    
    category = models.ForeignKey(Category, on_delete=models.SET_NULL, null=True, blank=True, related_name="assets")
    collection = models.ForeignKey(Collection, on_delete=models.SET_NULL, null=True, blank=True, related_name="assets")
    tags = models.ManyToManyField(Tag, related_name="assets", blank=True)

    photographer = models.CharField(max_length=255, blank=True)
    photographer_credit = models.CharField(max_length=255, blank=True)
    source = models.CharField(max_length=255, blank=True)
    copyright_holder = models.CharField(max_length=255, blank=True)
    publication_date = models.DateField(null=True, blank=True, db_index=True)
    capture_date = models.DateField(null=True, blank=True)

    class Meta:
        verbose_name = _("Digital Asset")
        verbose_name_plural = _("Digital Assets")

    def __str__(self):
        return f"{self.asset_number} - {self.title}"


class AssetMetadata(BaseModel):
    asset = models.OneToOneField(DigitalAsset, on_delete=models.CASCADE, related_name="metadata")
    keywords = models.TextField(blank=True)
    location = models.CharField(max_length=255, blank=True)
    county = models.CharField(max_length=100, blank=True)
    country = models.CharField(max_length=100, blank=True, default="Kenya")
    event_name = models.CharField(max_length=255, blank=True)
    historical_period = models.CharField(max_length=100, blank=True)
    headline = models.CharField(max_length=255, blank=True)
    language = models.CharField(max_length=50, blank=True, default="en")

    class Meta:
        verbose_name_plural = "Asset Metadata"

    def __str__(self):
        return f"Metadata for {self.asset.title}"


class AssetVariant(BaseModel):
    asset = models.ForeignKey(DigitalAsset, on_delete=models.CASCADE, related_name="variants")
    variant_name = models.CharField(max_length=100) # e.g., 'Thumbnail', 'Watermarked Preview', 'High Resolution', 'Original File'
    storage_path = models.CharField(max_length=500)
    mime_type = models.CharField(max_length=100)
    file_size = models.BigIntegerField() # in bytes
    checksum = models.CharField(max_length=64, blank=True) # e.g., SHA256

    def __str__(self):
        return f"{self.variant_name} - {self.asset.title}"
