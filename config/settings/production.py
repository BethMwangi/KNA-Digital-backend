"""Production settings (SDD §26, §29)."""

from .base import *  # noqa

DEBUG = False

# Static files served efficiently behind gunicorn
MIDDLEWARE.insert(1, "whitenoise.middleware.WhiteNoiseMiddleware")  # noqa: F405

# Media → Supabase Storage (S3-compatible). See core/storage_s3.py.
#
# Render (this deployment) still serves the live site — the self-hosted
# urithi.go.ke server that local-disk storage is built for isn't cut
# over yet (no ingestion has populated its disk). Render's filesystem
# has no media on it, so core.storage.Local*MediaStorage 404s every
# thumbnail there; Supabase still holds the real files. Switch back to
# core.storage.Local*MediaStorage (see git history for the settings
# below) only once the new server is actually serving traffic.
AWS_ACCESS_KEY_ID = env("SUPABASE_S3_ACCESS_KEY_ID")  # noqa: F405
AWS_SECRET_ACCESS_KEY = env("SUPABASE_S3_SECRET_ACCESS_KEY")  # noqa: F405
AWS_S3_ENDPOINT_URL = env("SUPABASE_S3_ENDPOINT_URL")  # noqa: F405
AWS_S3_REGION_NAME = env("SUPABASE_S3_REGION", default="us-east-1")  # noqa: F405
AWS_S3_ADDRESSING_STYLE = "path"  # Supabase requires path-style, not virtual-hosted
AWS_S3_FILE_OVERWRITE = False
AWS_DEFAULT_ACL = None  # ACLs set per-storage-class instead (see core/storage_s3.py)

SUPABASE_PUBLIC_BUCKET = env("SUPABASE_PUBLIC_BUCKET", default="public")  # noqa: F405
SUPABASE_PRIVATE_BUCKET = env("SUPABASE_PRIVATE_BUCKET", default="private")  # noqa: F405

STORAGES = {
    **STORAGES,  # noqa: F405
    "staticfiles": {"BACKEND": "whitenoise.storage.CompressedManifestStaticFilesStorage"},
    "public_media": {"BACKEND": "core.storage_s3.SupabasePublicMediaStorage"},
    "private_media": {"BACKEND": "core.storage_s3.SupabasePrivateMediaStorage"},
}
MEDIA_SERVE_VIA_NGINX = env.bool("MEDIA_SERVE_VIA_NGINX", default=False)  # noqa: F405

# HTTPS everywhere (behind Nginx / Railway proxy)
SECURE_PROXY_SSL_HEADER = ("HTTP_X_FORWARDED_PROTO", "https")
SECURE_SSL_REDIRECT = True
SESSION_COOKIE_SECURE = True
CSRF_COOKIE_SECURE = True
SECURE_HSTS_SECONDS = 31536000
SECURE_HSTS_INCLUDE_SUBDOMAINS = True
SECURE_HSTS_PRELOAD = True
SECURE_CONTENT_TYPE_NOSNIFF = True
