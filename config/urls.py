"""Root URL configuration — all business APIs are versioned under /api/v1 (SDD §16.4)."""

from django.contrib import admin
from django.urls import include, path
from drf_spectacular.views import SpectacularAPIView, SpectacularRedocView, SpectacularSwaggerView

urlpatterns = [
    path("admin/", admin.site.urls),
    # API v1
    path("api/v1/", include("apps.accounts.urls")),
    # Future modules mount here without touching existing routes:
    path("api/v1/", include("apps.assets.urls")),
    # path("api/v1/", include("apps.orders.urls")),
    path("api/schema/", SpectacularAPIView.as_view(), name="schema"),
    path("docs/", SpectacularSwaggerView.as_view(url_name="schema"), name="swagger-ui"),
    path("redoc/", SpectacularRedocView.as_view(url_name="schema"), name="redoc"),
]
