"""
Downloads API views (SDD §16.14).

Customers can list their purchased downloads and generate secure
signed URLs to fetch the high-resolution files.
"""

from drf_spectacular.utils import extend_schema, inline_serializer
from rest_framework import generics, permissions, serializers, status
from rest_framework.response import Response

from apps.accounts.permissions import IsAccountActive
from apps.assets.models import AssetVariant

from .models import Download
from .serializers import DownloadSerializer


def api_response(*, message: str, data=None, success: bool = True, status_code=status.HTTP_200_OK):
    """Standard response envelope (SDD §16.2)."""
    return Response(
        {"success": success, "message": message, "data": data or {}}, status=status_code
    )


class DownloadListView(generics.ListAPIView):
    """GET /api/v1/downloads/ — list my purchased downloads."""

    serializer_class = DownloadSerializer
    permission_classes = [permissions.IsAuthenticated, IsAccountActive]

    def get_queryset(self):
        user = self.request.user
        if not user or not user.is_authenticated:
            return Download.objects.none()
        return Download.objects.filter(user=user).select_related("asset", "license", "order")

    def list(self, request, *args, **kwargs):
        response = super().list(request, *args, **kwargs)
        return api_response(message="Downloads retrieved.", data=response.data)


class DownloadLinkView(generics.GenericAPIView):
    """
    GET /api/v1/downloads/{id}/link/ — get a secure signed download URL.

    Checks that the user owns the download and hasn't exceeded the limit.
    """

    permission_classes = [permissions.IsAuthenticated, IsAccountActive]

    @extend_schema(
        summary="Generate download link",
        description="Returns a time-limited signed URL to download the purchased high-resolution asset.",
        responses={
            200: inline_serializer(
                name="DownloadLinkResponse",
                fields={
                    "download_url": serializers.URLField(),
                    "file_name": serializers.CharField(),
                    "mime_type": serializers.CharField(),
                    "file_size": serializers.IntegerField(),
                    "downloads_remaining": serializers.IntegerField(),
                },
            )
        },
    )
    def get(self, request, pk):
        try:
            download = Download.objects.get(id=pk, user=request.user)
        except Download.DoesNotExist:
            return api_response(
                success=False,
                message="Download not found.",
                status_code=status.HTTP_404_NOT_FOUND,
            )

        if not download.can_download:
            return api_response(
                success=False,
                message="Download limit reached.",
                status_code=status.HTTP_403_FORBIDDEN,
            )

        # Get the high-res variant for this asset
        variant = AssetVariant.objects.filter(
            asset=download.asset,
            variant_name__icontains="high",
        ).first()

        if not variant:
            # Fallback to any variant
            variant = AssetVariant.objects.filter(asset=download.asset).first()

        if not variant:
            return api_response(
                success=False,
                message="No downloadable file found for this asset.",
                status_code=status.HTTP_404_NOT_FOUND,
            )

        signed_url = download.generate_signed_url(variant)
        download.record_download()

        return api_response(
            message="Download link generated.",
            data={
                "download_url": signed_url,
                "file_name": f"{download.asset.asset_number}.{variant.mime_type.split('/')[-1]}",
                "mime_type": variant.mime_type,
                "file_size": variant.file_size,
                "downloads_remaining": download.downloads_remaining,
            },
        )
