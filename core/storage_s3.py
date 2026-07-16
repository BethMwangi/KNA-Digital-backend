"""
Supabase Storage backends (S3-compatible) — wired in only by
config/settings/production.py. Two buckets mirror the local public/private
split in core/storage.py: public = watermarked previews (world-readable),
private = purchasable originals/high-res (signed URLs only, short expiry).

Kept in its own module (rather than core/storage.py) so importing it — and
therefore requiring `django-storages`/`boto3` — never happens in local dev,
where STORAGES only ever references the local classes.

Needs SUPABASE_S3_ENDPOINT_URL, SUPABASE_S3_ACCESS_KEY_ID,
SUPABASE_S3_SECRET_ACCESS_KEY, SUPABASE_S3_REGION, SUPABASE_PUBLIC_BUCKET,
SUPABASE_PRIVATE_BUCKET — see .env.example.
"""

from django.conf import settings
from storages.backends.s3boto3 import S3Boto3Storage


class SupabasePublicMediaStorage(S3Boto3Storage):
    """
    Uploads go through the S3-compatible protocol (PutObject) same as any
    S3Boto3Storage. Reads do NOT: Supabase's S3 endpoint (/storage/v1/s3/…)
    always demands a signed request, public bucket or not — "public" only
    applies to Supabase's own native REST path (/storage/v1/object/public/…),
    which serves unsigned reads. So .url() is overridden to build that path
    instead of the (always-signed) S3-style URL the base class would give.
    """

    default_acl = "public-read"
    querystring_auth = False
    file_overwrite = True

    def __init__(self, **kwargs):
        kwargs.setdefault("bucket_name", settings.SUPABASE_PUBLIC_BUCKET)
        super().__init__(**kwargs)

    def url(self, name, parameters=None, expire=None, http_method=None):
        base = settings.AWS_S3_ENDPOINT_URL.replace("/storage/v1/s3", "/storage/v1/object/public")
        return f"{base}/{self.bucket_name}/{name}"


class SupabasePrivateMediaStorage(S3Boto3Storage):
    default_acl = "private"
    querystring_auth = True  # every .url() call returns a presigned link
    querystring_expire = 3600
    file_overwrite = True

    def __init__(self, **kwargs):
        kwargs.setdefault("bucket_name", settings.SUPABASE_PRIVATE_BUCKET)
        super().__init__(**kwargs)
