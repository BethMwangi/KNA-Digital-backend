"""Production settings (SDD §26, §29)."""

from .base import *  # noqa

DEBUG = False

# Static files served efficiently behind gunicorn
MIDDLEWARE.insert(1, "whitenoise.middleware.WhiteNoiseMiddleware")  # noqa: F405

# Media storage backend — chosen per-deployment by MEDIA_BACKEND, never by
# which code is checked out. Render and the self-hosted urithi.go.ke server
# run the exact same `main` branch; only their .env files differ. This is
# deliberate: a hardcoded switch here is what broke Render's thumbnails
# once already (a commit meant only for the new server took effect on
# Render too, since both read production.py). Defaulting to "s3" means
# Render is safe by default even if this file changes again — it would
# have to opt in via its own env to ever pick up "local".
MEDIA_BACKEND = env("MEDIA_BACKEND", default="s3")  # noqa: F405 — "s3" | "local"

if MEDIA_BACKEND == "local":
    # Self-hosted server: media on local disk, served by nginx. Private
    # (paid) files go through SecureMediaDownloadView + nginx
    # X-Accel-Redirect — see apps/downloads/models.py::generate_signed_url
    # for why a signed, expiring token is required (local disk has no
    # presigned-URL equivalent to S3).
    STORAGES = {
        **STORAGES,  # noqa: F405
        "staticfiles": {"BACKEND": "whitenoise.storage.CompressedManifestStaticFilesStorage"},
        "public_media": {"BACKEND": "core.storage.LocalPublicMediaStorage"},
        "private_media": {"BACKEND": "core.storage.LocalPrivateMediaStorage"},
    }
    MEDIA_SERVE_VIA_NGINX = env.bool("MEDIA_SERVE_VIA_NGINX", default=True)  # noqa: F405
else:
    # Render (current live site): Supabase Storage (S3-compatible). See
    # core/storage_s3.py.
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
