from django.core.files.storage import storages
from rest_framework import serializers

from .models import AssetMetadata, AssetVariant, Category, Collection, DigitalAsset, Tag


def public_variant_url(asset, variant_name: str) -> str:
    """URL for a watermarked public variant; empty string if not generated yet.
    Uses prefetched variants when available (no extra query per asset).
    Goes through the "public_media" storage alias so this works unchanged
    whether files live on local disk (dev) or Supabase Storage (prod)."""
    for v in asset.variants.all():
        if v.variant_name == variant_name:
            if v.storage_path.startswith(("http://", "https://")):
                return v.storage_path  # just synced, not yet mirrored (hotlink)
            return storages["public_media"].url(v.storage_path)
    return ""


def _cover_url(obj) -> str:
    """Banner image for a Collection/Category card: the curated cover_asset
    if an editor picked one, else the newest published asset. Uses the
    1200px 'preview' variant (bigger than the grid thumbnail)."""
    asset = obj.cover_asset
    if asset is None:
        asset = (
            obj.assets.filter(
                status=DigitalAsset.Status.PUBLISHED,
                visibility=DigitalAsset.Visibility.PUBLIC,
            )
            .prefetch_related("variants")
            .order_by("-created_at")
            .first()
        )
    if asset is None:
        return ""
    return public_variant_url(asset, "preview") or public_variant_url(asset, "thumbnail")


class _CardCountMixin(serializers.ModelSerializer):
    """count = published+public assets. Reads the viewset's annotation when
    present (no extra query); falls back to a COUNT for other callers."""

    count = serializers.SerializerMethodField()
    cover = serializers.SerializerMethodField()

    def get_count(self, obj) -> int:
        annotated = getattr(obj, "asset_count", None)
        if annotated is not None:
            return annotated
        return obj.assets.filter(
            status=DigitalAsset.Status.PUBLISHED,
            visibility=DigitalAsset.Visibility.PUBLIC,
        ).count()

    def get_cover(self, obj) -> str:
        return _cover_url(obj)


class CategorySerializer(_CardCountMixin):
    class Meta:
        model = Category
        fields = ["id", "name", "slug", "description", "count", "cover", "created_at", "updated_at"]


class CollectionSerializer(_CardCountMixin):
    class Meta:
        model = Collection
        fields = ["id", "name", "slug", "description", "count", "cover", "created_at", "updated_at"]


class TagSerializer(serializers.ModelSerializer):
    class Meta:
        model = Tag
        fields = ["id", "name", "slug"]


class AssetVariantPublicSerializer(serializers.ModelSerializer):
    """Public-facing variant serializer — never exposes internal storage_path."""

    class Meta:
        model = AssetVariant
        fields = ["id", "variant_name", "mime_type", "file_size"]


class AssetMetadataSerializer(serializers.ModelSerializer):
    class Meta:
        model = AssetMetadata
        fields = [
            "keywords",
            "location",
            "county",
            "country",
            "event_name",
            "historical_period",
            "headline",
            "language",
        ]


# ------------------------------------------------------------------ #
# List (lightweight) vs Detail (full) asset serializers
# ------------------------------------------------------------------ #
class DigitalAssetListSerializer(serializers.ModelSerializer):
    category = CategorySerializer(read_only=True)
    collection = CollectionSerializer(read_only=True)
    tags = TagSerializer(many=True, read_only=True)
    thumbnail = serializers.SerializerMethodField()
    currency = serializers.SerializerMethodField()

    def get_thumbnail(self, obj):
        return public_variant_url(obj, "thumbnail") or public_variant_url(obj, "preview")

    def get_currency(self, obj):
        return "KES"

    class Meta:
        model = DigitalAsset
        fields = [
            "id",
            "asset_number",
            "title",
            "asset_type",
            "status",
            "visibility",
            "category",
            "collection",
            "tags",
            "photographer",
            "thumbnail",
            "price",
            "currency",
            "publication_date",
            "created_at",
        ]


class DigitalAssetDetailSerializer(serializers.ModelSerializer):
    category = CategorySerializer(read_only=True)
    collection = CollectionSerializer(read_only=True)
    tags = TagSerializer(many=True, read_only=True)
    metadata = AssetMetadataSerializer(read_only=True)
    variants = AssetVariantPublicSerializer(many=True, read_only=True)
    thumbnail = serializers.SerializerMethodField()
    image = serializers.SerializerMethodField()
    currency = serializers.SerializerMethodField()

    def get_thumbnail(self, obj):
        return public_variant_url(obj, "thumbnail")

    def get_image(self, obj):
        return public_variant_url(obj, "preview") or public_variant_url(obj, "thumbnail")

    def get_currency(self, obj):
        return "KES"

    class Meta:
        model = DigitalAsset
        fields = [
            "id",
            "asset_number",
            "title",
            "description",
            "caption",
            "asset_type",
            "status",
            "visibility",
            "category",
            "collection",
            "tags",
            "photographer",
            "photographer_credit",
            "source",
            "copyright_holder",
            "publication_date",
            "capture_date",
            "metadata",
            "variants",
            "thumbnail",
            "image",
            "price",
            "currency",
            "created_at",
            "updated_at",
        ]


# ------------------------------------------------------------------ #
# Write serializer for Content Editors / Admins
# ------------------------------------------------------------------ #
class DigitalAssetCreateSerializer(serializers.ModelSerializer):
    """Used by Content Editors to create/update assets."""

    category_id = serializers.UUIDField(required=False, allow_null=True)
    collection_id = serializers.UUIDField(required=False, allow_null=True)
    tag_ids = serializers.ListField(child=serializers.UUIDField(), required=False, default=list)

    class Meta:
        model = DigitalAsset
        fields = [
            "asset_number",
            "title",
            "description",
            "caption",
            "asset_type",
            "status",
            "visibility",
            "category_id",
            "collection_id",
            "tag_ids",
            "photographer",
            "photographer_credit",
            "source",
            "copyright_holder",
            "publication_date",
            "capture_date",
        ]

    def create(self, validated_data):
        tag_ids = validated_data.pop("tag_ids", [])
        asset = DigitalAsset.objects.create(**validated_data)
        if tag_ids:
            asset.tags.set(Tag.objects.filter(id__in=tag_ids))
        return asset

    def update(self, instance, validated_data):
        tag_ids = validated_data.pop("tag_ids", None)
        for attr, value in validated_data.items():
            setattr(instance, attr, value)
        instance.save()
        if tag_ids is not None:
            instance.tags.set(Tag.objects.filter(id__in=tag_ids))
        return instance
