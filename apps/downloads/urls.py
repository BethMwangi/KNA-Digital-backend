"""Downloads URL routes."""

from django.urls import path

from . import views

urlpatterns = [
    path("downloads/", views.DownloadListView.as_view(), name="download-list"),
    path("downloads/<uuid:pk>/link/", views.DownloadLinkView.as_view(), name="download-link"),
]
