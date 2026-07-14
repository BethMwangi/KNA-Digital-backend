"""
Assets API views.

Follows SDD §16.2 response envelope and RBAC from accounts.permissions.
"""

from django_filters.rest_framework import DjangoFilterBackend
from rest_framework import permissions, status, viewsets
from rest_framework.decorators import action
from rest_framework.filters import OrderingFilter, SearchFilter
from rest_framework.response import Response

from apps.accounts.permissions import IsContentEditorOrAbove

from .models import Category, Collection, DigitalAsset, Tag
from .serializers import (
    CategorySerializer,
    CollectionSerializer,
    DigitalAssetCreateSerializer,
    DigitalAssetDetailSerializer,
    DigitalAssetListSerializer,
    TagSerializer,
)


def api_response(*, message: str, data=None, success: bool = True, status_code=status.HTTP_200_OK):
    """Standard response envelope (SDD §16.2)."""
    return Response(
        {"success": success, "message": message, "data": data or {}}, status=status_code
    )


class CategoryViewSet(viewsets.ReadOnlyModelViewSet):
    queryset = Category.objects.all()
    serializer_class = CategorySerializer
    permission_classes = [permissions.AllowAny]

    def list(self, request, *args, **kwargs):
        response = super().list(request, *args, **kwargs)
        return api_response(message="Categories retrieved.", data=response.data)

    def retrieve(self, request, *args, **kwargs):
        instance = self.get_object()
        serializer = self.get_serializer(instance)
        return api_response(message="Category retrieved.", data=serializer.data)


class CollectionViewSet(viewsets.ReadOnlyModelViewSet):
    queryset = Collection.objects.all()
    serializer_class = CollectionSerializer
    permission_classes = [permissions.AllowAny]

    def list(self, request, *args, **kwargs):
        response = super().list(request, *args, **kwargs)
        return api_response(message="Collections retrieved.", data=response.data)

    def retrieve(self, request, *args, **kwargs):
        instance = self.get_object()
        serializer = self.get_serializer(instance)
        return api_response(message="Collection retrieved.", data=serializer.data)


class TagViewSet(viewsets.ReadOnlyModelViewSet):
    queryset = Tag.objects.all()
    serializer_class = TagSerializer
    permission_classes = [permissions.AllowAny]

    def list(self, request, *args, **kwargs):
        response = super().list(request, *args, **kwargs)
        return api_response(message="Tags retrieved.", data=response.data)

    def retrieve(self, request, *args, **kwargs):
        instance = self.get_object()
        serializer = self.get_serializer(instance)
        return api_response(message="Tag retrieved.", data=serializer.data)


class DigitalAssetViewSet(viewsets.ModelViewSet):
    queryset = (
        DigitalAsset.objects.filter(
            status=DigitalAsset.Status.PUBLISHED,
            visibility=DigitalAsset.Visibility.PUBLIC,
        )
        .select_related("category", "collection", "metadata")
        .prefetch_related("tags", "variants")
    )
    # prefetch related fields to avoid N+1 queries
    filter_backends = [DjangoFilterBackend, SearchFilter, OrderingFilter]
    filterset_fields = ["category", "collection", "asset_type", "publication_date"]
    search_fields = ["title", "description", "caption", "metadata__keywords"]
    ordering_fields = ["publication_date", "created_at"]
    ordering = ["-created_at"]

    def get_serializer_class(self):
        if self.action == "retrieve":
            return DigitalAssetDetailSerializer
        if self.action in ["create", "update", "partial_update"]:
            return DigitalAssetCreateSerializer
        return DigitalAssetListSerializer

    def get_permissions(self):
        if self.action in ["list", "retrieve", "featured", "latest", "search"]:
            return [permissions.AllowAny()]
        # create, update, partial_update, destroy, publish, archive → editor+
        return [permissions.IsAuthenticated(), IsContentEditorOrAbove()]

    def get_queryset(self):
        user = self.request.user
        if user.is_authenticated and (user.is_staff or getattr(user, "is_content_editor", False)):
            return (
                DigitalAsset.objects.all()
                .select_related("category", "collection", "metadata")
                .prefetch_related("tags", "variants")
            )
        # note :objects not all_objects because we want to show only published and public assets to non-staff users
        return super().get_queryset()

    def list(self, request, *args, **kwargs):
        response = super().list(request, *args, **kwargs)
        return api_response(message="Assets retrieved.", data=response.data)

    def retrieve(self, request, *args, **kwargs):
        instance = self.get_object()
        serializer = self.get_serializer(instance)
        return api_response(message="Asset retrieved.", data=serializer.data)

    def create(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        serializer.save()
        return api_response(
            message="Asset created.",
            data=serializer.data,
            status_code=status.HTTP_201_CREATED,
        )

    @action(detail=False, methods=["get"])
    def featured(self, request):
        featured_assets = self.get_queryset()[:5]
        serializer = self.get_serializer(featured_assets, many=True)
        return api_response(message="Featured assets retrieved.", data=serializer.data)

    @action(detail=False, methods=["get"])
    def latest(self, request):
        latest_assets = self.get_queryset().order_by("-publication_date")[:10]
        serializer = self.get_serializer(latest_assets, many=True)
        return api_response(message="Latest assets retrieved.", data=serializer.data)

    @action(detail=False, methods=["get"])
    def search(self, request):
        queryset = self.filter_queryset(self.get_queryset())
        page = self.paginate_queryset(queryset)
        if page is not None:
            serializer = self.get_serializer(page, many=True)
            return self.get_paginated_response(serializer.data)
        serializer = self.get_serializer(queryset, many=True)
        return api_response(message="Search results.", data=serializer.data)

    @action(detail=True, methods=["post"])
    def publish(self, request, pk=None):
        asset = self.get_object()
        if not asset.variants.filter(variant_name__in=["thumbnail", "preview"]).exists():
            return api_response(
                success=False,
                message="Cannot publish: no thumbnail/preview has been generated for this asset.",
                status_code=status.HTTP_409_CONFLICT,
            )
        asset.status = DigitalAsset.Status.PUBLISHED
        asset.save(update_fields=["status", "updated_at"])
        return api_response(
            message="Asset published.", data={"id": str(asset.id), "status": asset.status}
        )

    # guard the publish action to ensure that the asset has at least one variant with the name "thumbnail" or "preview" before allowing it to be published. If not, return a 409 Conflict response with an appropriate message.

    @action(detail=True, methods=["post"])
    def archive(self, request, pk=None):
        asset = self.get_object()
        asset.status = DigitalAsset.Status.ARCHIVED
        asset.save(update_fields=["status", "updated_at"])
        return api_response(
            message="Asset archived.", data={"id": str(asset.id), "status": asset.status}
        )
