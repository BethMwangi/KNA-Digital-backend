"""
Use wherever a variant is rendered (serializers, templates):

    from apps.ingestion.urls_helper import variant_url
    image = variant_url(asset.variants.filter(variant_name="preview").first())

Handles both states transparently:
  - external URL (just ingested, not yet mirrored) → returned as-is
  - bucket path (mirrored)                         → our public URL
"""

from django.core.files.storage import storages


def variant_url(variant) -> str:
    if variant is None or not variant.storage_path:
        return ""
    if variant.storage_path.startswith(("http://", "https://")):
        return variant.storage_path
    return storages["public_media"].url(variant.storage_path)
