from django.urls import include, path
from rest_framework.routers import DefaultRouter

from .views import CategoryViewSet, CollectionViewSet, DigitalAssetViewSet, TagViewSet

router = DefaultRouter()
router.register(r"categories", CategoryViewSet, basename="category")
router.register(r"collections", CollectionViewSet, basename="collection")
router.register(r"tags", TagViewSet, basename="tag")
# Register assets under 'assets' prefix
router.register(r"assets", DigitalAssetViewSet, basename="asset")

urlpatterns = [
    path("", include(router.urls)),
]
