from rest_framework import serializers

from .models import Download


class DownloadSerializer(serializers.ModelSerializer):
    asset_title = serializers.CharField(source="asset.title", read_only=True)
    license_name = serializers.CharField(source="license.name", read_only=True)
    downloads_remaining = serializers.IntegerField(read_only=True)
    can_download = serializers.BooleanField(read_only=True)

    class Meta:
        model = Download
        fields = [
            "id",
            "asset",
            "asset_title",
            "license",
            "license_name",
            "order",
            "download_count",
            "max_downloads",
            "downloads_remaining",
            "can_download",
            "created_at",
        ]
