"""
Assets API views.

Follows SDD §16.2 response envelope and RBAC from accounts.permissions.
"""

from django.conf import settings
from django.db.models import Count, Q
from django.utils.decorators import method_decorator
from django.views.decorators.cache import cache_page
from django.views.decorators.vary import vary_on_headers
from django_filters.rest_framework import DjangoFilterBackend
from rest_framework import permissions, status, viewsets
from rest_framework.decorators import action
from rest_framework.filters import OrderingFilter, SearchFilter
from rest_framework.response import Response

from apps.accounts.permissions import IsContentEditorOrAbove

from .filters import DigitalAssetFilter
from .models import Category, Collection, DigitalAsset, Tag
from .search import search_assets, suggest_assets
from .serializers import (
    AssetSuggestSerializer,
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


# Page-cache for public reads (catalogue data changes rarely). Asset
# endpoints must also vary on Authorization: staff see drafts, so their
# JWT'd responses get separate cache entries from the shared anonymous one.
cache_public = method_decorator(cache_page(settings.API_CACHE_TTL))
vary_auth = method_decorator(vary_on_headers("Authorization"))

# Card data for the storefront: count only what visitors can actually see.
_PUBLISHED_COUNT = Count(
    "assets",
    filter=Q(
        assets__status=DigitalAsset.Status.PUBLISHED,
        assets__visibility=DigitalAsset.Visibility.PUBLIC,
        assets__deleted_at__isnull=True,
    ),
)


class CategoryViewSet(viewsets.ReadOnlyModelViewSet):
    queryset = Category.objects.annotate(asset_count=_PUBLISHED_COUNT).select_related("cover_asset")
    serializer_class = CategorySerializer
    permission_classes = [permissions.AllowAny]

    @cache_public
    def list(self, request, *args, **kwargs):
        response = super().list(request, *args, **kwargs)
        return api_response(message="Categories retrieved.", data=response.data)

    @cache_public
    def retrieve(self, request, *args, **kwargs):
        instance = self.get_object()
        serializer = self.get_serializer(instance)
        return api_response(message="Category retrieved.", data=serializer.data)


class CollectionViewSet(viewsets.ReadOnlyModelViewSet):
    queryset = Collection.objects.annotate(asset_count=_PUBLISHED_COUNT).select_related(
        "cover_asset"
    )
    serializer_class = CollectionSerializer
    permission_classes = [permissions.AllowAny]

    @cache_public
    def list(self, request, *args, **kwargs):
        response = super().list(request, *args, **kwargs)
        return api_response(message="Collections retrieved.", data=response.data)

    @cache_public
    def retrieve(self, request, *args, **kwargs):
        instance = self.get_object()
        serializer = self.get_serializer(instance)
        return api_response(message="Collection retrieved.", data=serializer.data)


class TagViewSet(viewsets.ReadOnlyModelViewSet):
    queryset = Tag.objects.all()
    serializer_class = TagSerializer
    permission_classes = [permissions.AllowAny]

    @cache_public
    def list(self, request, *args, **kwargs):
        response = super().list(request, *args, **kwargs)
        return api_response(message="Tags retrieved.", data=response.data)

    @cache_public
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
    filterset_class = DigitalAssetFilter
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
        if self.action in ["list", "retrieve", "featured", "latest", "search", "suggest"]:
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

    @vary_auth
    @cache_public
    def list(self, request, *args, **kwargs):
        response = super().list(request, *args, **kwargs)
        return api_response(message="Assets retrieved.", data=response.data)

    @vary_auth
    @cache_public
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
    @vary_auth
    @cache_public
    def featured(self, request):
        featured_assets = self.get_queryset()[:5]
        serializer = self.get_serializer(featured_assets, many=True)
        return api_response(message="Featured assets retrieved.", data=serializer.data)

    @action(detail=False, methods=["get"])
    @vary_auth
    @cache_public
    def latest(self, request):
        latest_assets = self.get_queryset().order_by("-publication_date")[:10]
        serializer = self.get_serializer(latest_assets, many=True)
        return api_response(message="Latest assets retrieved.", data=serializer.data)

    @action(detail=False, methods=["get"])
    @vary_auth
    def search(self, request):
        """
        Full-text search, ranked by relevance, with an automatic
        typo-tolerant fallback (see apps.assets.search). Same
        category/collection/asset_type/date_from/date_to/year narrowing
        as the list endpoint (via DigitalAssetFilter), applied before
        ranking. Empty ?q= just returns the newest first.
        """
        query = (request.query_params.get("q") or request.query_params.get("search") or "").strip()
        queryset = DigitalAssetFilter(request.GET, queryset=self.get_queryset()).qs

        if query:
            queryset, match_type = search_assets(query, queryset)
        else:
            queryset, match_type = queryset.order_by("-created_at"), "none"

        page = self.paginate_queryset(queryset)
        if page is not None:
            serializer = self.get_serializer(page, many=True)
            paginated = self.get_paginated_response(serializer.data)
            paginated.data["query"] = query
            paginated.data["match_type"] = match_type
            return api_response(message="Search results.", data=paginated.data)

        serializer = self.get_serializer(queryset, many=True)
        return api_response(
            message="Search results.",
            data={"results": serializer.data, "query": query, "match_type": match_type},
        )

    @action(detail=False, methods=["get"])
    @vary_auth
    def suggest(self, request):
        """GET /api/v1/assets/suggest/?q=ken — top 8 matches for a live
        as-you-type dropdown. Deliberately unpaginated and lightweight.
        Always {"results": [...]} (never a bare list) — api_response's
        `data or {}` would otherwise collapse a genuinely empty list to
        {}, which is surprising for a frontend expecting an array."""
        query = (request.query_params.get("q") or "").strip()
        if not query:
            return api_response(message="Suggestions retrieved.", data={"results": []})
        results = suggest_assets(query, self.get_queryset())
        serializer = AssetSuggestSerializer(results, many=True)
        return api_response(message="Suggestions retrieved.", data={"results": serializer.data})

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
