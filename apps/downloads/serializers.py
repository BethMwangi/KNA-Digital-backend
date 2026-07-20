from rest_framework import serializers

from apps.assets.serializers import public_variant_url

from .models import Download


class DownloadSerializer(serializers.ModelSerializer):
    asset_title = serializers.CharField(source="asset.title", read_only=True)
    asset_number = serializers.CharField(source="asset.asset_number", read_only=True)
    thumbnail = serializers.SerializerMethodField()
    license_name = serializers.CharField(source="license.name", read_only=True)
    order_number = serializers.CharField(source="order.order_number", read_only=True)
    downloads_remaining = serializers.IntegerField(read_only=True)
    can_download = serializers.BooleanField(read_only=True)

    def get_thumbnail(self, obj):
        return public_variant_url(obj.asset, "thumbnail") or public_variant_url(
            obj.asset, "preview"
        )

    class Meta:
        model = Download
        fields = [
            "id",
            "asset",
            "asset_title",
            "asset_number",
            "thumbnail",
            "license",
            "license_name",
            "order",
            "order_number",
            "download_count",
            "max_downloads",
            "downloads_remaining",
            "can_download",
            "created_at",
        ]
