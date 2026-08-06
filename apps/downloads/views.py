"""
Downloads API views (SDD §16.14).

Customers can list their purchased downloads and generate secure
signed URLs to fetch the high-resolution files.
"""

from django.conf import settings
from django.core.files.storage import storages
from django.core.signing import BadSignature, SignatureExpired, TimestampSigner
from django.http import FileResponse, Http404, HttpResponse
from django.views import View
from drf_spectacular.utils import extend_schema, inline_serializer
from rest_framework import generics, permissions, serializers, status
from rest_framework.response import Response

from apps.accounts.permissions import IsAccountActive
from apps.assets.models import AssetVariant

from .models import DOWNLOAD_TOKEN_MAX_AGE, DOWNLOAD_TOKEN_SALT, Download
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
        return (
            Download.objects.filter(user=user)
            .select_related("asset", "license", "order")
            .prefetch_related("asset__variants")
        )

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
                    "url": serializers.URLField(),
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

        if download.external_download_link:
            return api_response(
                message="Download link generated.",
                data={
                    "url": download.external_download_link,
                    "download_url": download.external_download_link,
                    "file_name": download.asset.asset_number or download.asset.title,
                    "mime_type": "",
                    "file_size": 0,
                    "downloads_remaining": download.downloads_remaining,
                    "external_status": download.external_download_status,
                    "external_download_counts": download.external_download_counts,
                },
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
                "url": signed_url,
                "download_url": signed_url,
                "file_name": f"{download.asset.asset_number}.{variant.mime_type.split('/')[-1]}",
                "mime_type": variant.mime_type,
                "file_size": variant.file_size,
                "downloads_remaining": download.downloads_remaining,
            },
        )


class SecureMediaDownloadView(View):
    """
    GET /api/v1/secure-media/<token>/ — serves a private (paid) file
    given a signed token from Download.generate_signed_url(). Only used
    when "private_media" is local-disk storage (no native presigned-URL
    support) — see that method for why.

    No further auth/entitlement check happens here: possession of a
    valid, unexpired token *is* the authorization, exactly like an S3
    presigned URL. Entitlement was already checked once, in
    DownloadLinkView, at the moment the token was issued.
    """

    def get(self, request, token):
        try:
            variant_id = TimestampSigner(salt=DOWNLOAD_TOKEN_SALT).unsign(
                token, max_age=DOWNLOAD_TOKEN_MAX_AGE
            )
        except (BadSignature, SignatureExpired) as exc:
            raise Http404("Invalid or expired download link.") from exc

        variant = AssetVariant.objects.filter(id=variant_id).first()
        if variant is None:
            raise Http404("File not found.")

        storage = storages["private_media"]
        if not storage.exists(variant.storage_path):
            raise Http404("File not found.")

        if getattr(settings, "MEDIA_SERVE_VIA_NGINX", False):
            # Hand the actual byte transfer off to nginx — Python never
            # touches the file contents. nginx must have a matching
            # `internal` location for /internal/private-media/.
            response = HttpResponse(content_type=variant.mime_type)
            response["X-Accel-Redirect"] = f"/internal/private-media/{variant.storage_path}"
            return response

        return FileResponse(
            storage.open(variant.storage_path, "rb"), content_type=variant.mime_type
        )
