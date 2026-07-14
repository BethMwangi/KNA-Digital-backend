"""
Local filesystem media storage, split into public/private "buckets" so the
same code (import_local_tiffs, public_variant_url, generate_signed_url)
works identically whether files land on local disk (dev) or Supabase
Storage (prod) — see core/storage_s3.py for the production backends.

Referenced via the STORAGES["public_media"]/["private_media"] aliases in
settings, never imported directly — code should always go through
django.core.files.storage.storages["public_media" | "private_media"].
"""

from django.conf import settings
from django.core.files.storage import FileSystemStorage


class LocalPublicMediaStorage(FileSystemStorage):
    def __init__(self, **kwargs):
        kwargs.setdefault("location", settings.MEDIA_ROOT / "public")
        kwargs.setdefault("base_url", f"{settings.BACKEND_URL}{settings.MEDIA_URL}public/")
        super().__init__(**kwargs)


class LocalPrivateMediaStorage(FileSystemStorage):
    def __init__(self, **kwargs):
        kwargs.setdefault("location", settings.MEDIA_ROOT / "private")
        kwargs.setdefault("base_url", f"{settings.BACKEND_URL}{settings.MEDIA_URL}private/")
        super().__init__(**kwargs)
