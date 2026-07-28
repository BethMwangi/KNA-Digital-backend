"""Production settings (SDD §26, §29)."""

from .base import *  # noqa

DEBUG = False

# Static files served efficiently behind gunicorn
MIDDLEWARE.insert(1, "whitenoise.middleware.WhiteNoiseMiddleware")  # noqa: F405

# Media → local disk, served by nginx (see core/storage.py). Public files
# are served directly by nginx for speed; private (paid) files go through
# SecureMediaDownloadView + nginx X-Accel-Redirect — see
# apps/downloads/models.py::generate_signed_url for why a signed,
# expiring token is required here (local disk has no presigned-URL
# equivalent to S3, so we build our own).
STORAGES = {
    **STORAGES,  # noqa: F405
    "staticfiles": {"BACKEND": "whitenoise.storage.CompressedManifestStaticFilesStorage"},
    "public_media": {"BACKEND": "core.storage.LocalPublicMediaStorage"},
    "private_media": {"BACKEND": "core.storage.LocalPrivateMediaStorage"},
}
MEDIA_SERVE_VIA_NGINX = env.bool("MEDIA_SERVE_VIA_NGINX", default=True)  # noqa: F405

# HTTPS everywhere (behind Nginx / Railway proxy)
SECURE_PROXY_SSL_HEADER = ("HTTP_X_FORWARDED_PROTO", "https")
SECURE_SSL_REDIRECT = True
SESSION_COOKIE_SECURE = True
CSRF_COOKIE_SECURE = True
SECURE_HSTS_SECONDS = 31536000
SECURE_HSTS_INCLUDE_SUBDOMAINS = True
SECURE_HSTS_PRELOAD = True
SECURE_CONTENT_TYPE_NOSNIFF = True
