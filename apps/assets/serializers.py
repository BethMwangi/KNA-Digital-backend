from rest_framework import serializers

from .models import AssetMetadata, AssetVariant, Category, Collection, DigitalAsset, Tag


class CategorySerializer(serializers.ModelSerializer):
    class Meta:
        model = Category
        fields = ["id", "name", "slug", "description", "created_at", "updated_at"]


class CollectionSerializer(serializers.ModelSerializer):
    class Meta:
        model = Collection
        fields = ["id", "name", "slug", "description", "created_at", "updated_at"]


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
            "publication_date",
            "created_at",
        ]


class DigitalAssetDetailSerializer(serializers.ModelSerializer):
    category = CategorySerializer(read_only=True)
    collection = CollectionSerializer(read_only=True)
    tags = TagSerializer(many=True, read_only=True)
    metadata = AssetMetadataSerializer(read_only=True)
    variants = AssetVariantPublicSerializer(many=True, read_only=True)

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
