"""
Base settings — shared across dev/staging/production (SDD §25).
Environment-specific values come from env vars (12-factor).
"""

from datetime import timedelta
from decimal import Decimal
from pathlib import Path

import environ

BASE_DIR = Path(__file__).resolve().parent.parent.parent

env = environ.Env(DEBUG=(bool, False))
environ.Env.read_env(BASE_DIR / ".env")

SECRET_KEY = env("SECRET_KEY")
DEBUG = env("DEBUG")
ALLOWED_HOSTS = env.list("ALLOWED_HOSTS", default=["localhost", "127.0.0.1"])

FRONTEND_URL = env("FRONTEND_URL", default="http://localhost:3000")

INSTALLED_APPS = [
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
    # Third-party
    "rest_framework",
    "rest_framework_simplejwt.token_blacklist",
    "corsheaders",
    "django_filters",
    "drf_spectacular",
    # Local apps
    "core",
    "apps.accounts",
    "apps.assets",
    "apps.ingestion",
    "apps.commerce",
]

MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    "corsheaders.middleware.CorsMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
]

ROOT_URLCONF = "config.urls"
WSGI_APPLICATION = "config.wsgi.application"

TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        "DIRS": [],
        "APP_DIRS": True,
        "OPTIONS": {
            "context_processors": [
                "django.template.context_processors.request",
                "django.contrib.auth.context_processors.auth",
                "django.contrib.messages.context_processors.messages",
            ],
        },
    },
]

# ------------------------------------------------------------------ #
# Database — PostgreSQL (Supabase in Phase One, per SDD ADR-003)
# DATABASE_URL=postgres://user:pass@host:5432/dbname
# ------------------------------------------------------------------ #
DATABASES = {"default": env.db("DATABASE_URL")}
DATABASES["default"]["CONN_MAX_AGE"] = 60

# ------------------------------------------------------------------ #
# Auth — custom user, Argon2 hashing (SDD ADR-005)
# ------------------------------------------------------------------ #
AUTH_USER_MODEL = "accounts.User"

PASSWORD_HASHERS = [
    "django.contrib.auth.hashers.Argon2PasswordHasher",
    "django.contrib.auth.hashers.PBKDF2PasswordHasher",
]

AUTH_PASSWORD_VALIDATORS = [
    {"NAME": "django.contrib.auth.password_validation.UserAttributeSimilarityValidator"},
    {
        "NAME": "django.contrib.auth.password_validation.MinimumLengthValidator",
        "OPTIONS": {"min_length": 10},
    },
    {"NAME": "django.contrib.auth.password_validation.CommonPasswordValidator"},
    {"NAME": "django.contrib.auth.password_validation.NumericPasswordValidator"},
]

# ------------------------------------------------------------------ #
# DRF + JWT (SDD §16.2, §16.20, ADR-005)
# ------------------------------------------------------------------ #
REST_FRAMEWORK = {
    "DEFAULT_AUTHENTICATION_CLASSES": (
        "rest_framework_simplejwt.authentication.JWTAuthentication",
    ),
    "DEFAULT_PERMISSION_CLASSES": ("rest_framework.permissions.IsAuthenticated",),
    "DEFAULT_FILTER_BACKENDS": (
        "django_filters.rest_framework.DjangoFilterBackend",
        "rest_framework.filters.SearchFilter",
        "rest_framework.filters.OrderingFilter",
    ),
    "DEFAULT_PAGINATION_CLASS": "rest_framework.pagination.PageNumberPagination",
    "PAGE_SIZE": 20,  # SDD §19.4
    "DEFAULT_THROTTLE_CLASSES": (
        "rest_framework.throttling.AnonRateThrottle",
        "rest_framework.throttling.UserRateThrottle",
    ),
    "DEFAULT_THROTTLE_RATES": {"anon": "60/min", "user": "300/min"},
    "DEFAULT_SCHEMA_CLASS": "core.schema.AppGroupedAutoSchema",
    "EXCEPTION_HANDLER": "core.exceptions.api_exception_handler",
}

SIMPLE_JWT = {
    "ACCESS_TOKEN_LIFETIME": timedelta(minutes=env.int("JWT_EXPIRE_MINUTES", default=30)),
    "REFRESH_TOKEN_LIFETIME": timedelta(days=7),
    "ROTATE_REFRESH_TOKENS": True,
    "BLACKLIST_AFTER_ROTATION": True,
    "UPDATE_LAST_LOGIN": False,  # handled explicitly in LoginView with audit log
    "AUTH_HEADER_TYPES": ("Bearer",),
    "SIGNING_KEY": env("JWT_SECRET", default=SECRET_KEY),
}

SPECTACULAR_SETTINGS = {
    "TITLE": "KNA Enterprise Digital Archive Commerce Platform API",
    "DESCRIPTION": "Phase One — public eCommerce platform for licensed multimedia assets.",
    "VERSION": "1.0.0",
    "SERVE_INCLUDE_SCHEMA": False,
}

# ------------------------------------------------------------------ #
# CORS — Next.js frontend
# ------------------------------------------------------------------ #
CORS_ALLOWED_ORIGINS = env.list("CORS_ALLOWED_ORIGINS", default=[FRONTEND_URL])
CORS_ALLOWED_ORIGIN_REGEXES = [r"^https://.*\.vercel\.app$"]
# ------------------------------------------------------------------ #
# Email (SDD §21) — console in dev, SMTP/provider in production
# ------------------------------------------------------------------ #
EMAIL_BACKEND = env("EMAIL_BACKEND", default="django.core.mail.backends.console.EmailBackend")
EMAIL_HOST = env("EMAIL_HOST", default="")
EMAIL_PORT = env.int("EMAIL_PORT", default=587)
EMAIL_HOST_USER = env("EMAIL_USERNAME", default="")
EMAIL_HOST_PASSWORD = env("EMAIL_PASSWORD", default="")
EMAIL_USE_TLS = True
DEFAULT_FROM_EMAIL = env("DEFAULT_FROM_EMAIL", default="no-reply@archive.kna.go.ke")

# ------------------------------------------------------------------ #
# I18N / static
# ------------------------------------------------------------------ #
LANGUAGE_CODE = "en-us"
TIME_ZONE = "Africa/Nairobi"
USE_I18N = True
USE_TZ = True
STATIC_URL = "static/"
STATIC_ROOT = BASE_DIR / "staticfiles"
DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"

# ------------------------------------------------------------------ #
# Logging (SDD §27)
# ------------------------------------------------------------------ #
LOGGING = {
    "version": 1,
    "disable_existing_loggers": False,
    "formatters": {
        "verbose": {"format": "{levelname} {asctime} {module} {message}", "style": "{"},
    },
    "handlers": {"console": {"class": "logging.StreamHandler", "formatter": "verbose"}},
    "root": {"handlers": ["console"], "level": env("LOG_LEVEL", default="INFO")},
}

MEDIA_ROOT = BASE_DIR / "media"
MEDIA_URL = "/media/"
BACKEND_URL = env("BACKEND_URL", default="http://localhost:8000")

# ------------------------------------------------------------------ #
# Media storage — public (watermarked, world-readable) vs private
# (purchasable originals, signed URLs only). Local disk in dev;
# production.py swaps these two aliases for Supabase Storage.
# ------------------------------------------------------------------ #
STORAGES = {
    "default": {"BACKEND": "django.core.files.storage.FileSystemStorage"},
    "staticfiles": {"BACKEND": "django.contrib.staticfiles.storage.StaticFilesStorage"},
    "public_media": {"BACKEND": "core.storage.LocalPublicMediaStorage"},
    "private_media": {"BACKEND": "core.storage.LocalPrivateMediaStorage"},
}

# ------------------------------------------------------------------ #
# Ingestion — live feed (apps/ingestion). Endpoint details are secrets:
# they live only in the environment, never in the repo.
# ------------------------------------------------------------------ #
URITHI_BASE_URL = env("URITHI_BASE_URL", default="")
URITHI_LIST_PATH = env("URITHI_LIST_PATH", default="")
URITHI_ACK_PATH = env("URITHI_ACK_PATH", default="")
# Copy source thumbnails into our own bucket (hybrid mirroring) so the
# storefront never depends on the source server's uptime. Turn off only
# as a launch-fast fallback — variants then keep hotlinking source URLs.
MIRROR_THUMBNAILS = env.bool("MIRROR_THUMBNAILS", default=True)
# Flat KES price applied to synced assets that have no price yet.
ASSET_DEFAULT_PRICE = Decimal(env("ASSET_DEFAULT_PRICE", default="1500.00"))

# ------------------------------------------------------------------ #
# Celery — RabbitMQ broker. ALWAYS_EAGER=True executes tasks inline;
# keep it True wherever no worker process runs (single-dyno deploys),
# set it False where one does (docker compose `worker` service).
# ------------------------------------------------------------------ #
CELERY_BROKER_URL = env("CELERY_BROKER_URL", default="amqp://guest:guest@localhost:5672//")
CELERY_TASK_ALWAYS_EAGER = env.bool("CELERY_TASK_ALWAYS_EAGER", default=True)
CELERY_TASK_SERIALIZER = "json"
CELERY_ACCEPT_CONTENT = ["json"]
CELERY_RESULT_BACKEND = None  # fire-and-forget tasks; no result store needed
CELERY_TIMEZONE = TIME_ZONE
CELERY_BROKER_CONNECTION_RETRY_ON_STARTUP = True
CELERY_TASK_ACKS_LATE = True  # re-deliver if a worker dies mid-task
CELERY_WORKER_PREFETCH_MULTIPLIER = 1

# ------------------------------------------------------------------ #
# Cache — Redis when REDIS_URL is set, in-process fallback otherwise.
# Used for public read endpoints (assets/categories/collections change
# rarely, so short TTLs cut most DB round-trips).
# ------------------------------------------------------------------ #
REDIS_URL = env("REDIS_URL", default="")
if REDIS_URL:
    CACHES = {
        "default": {
            "BACKEND": "django.core.cache.backends.redis.RedisCache",
            "LOCATION": REDIS_URL,
            "KEY_PREFIX": "kna",
        }
    }
else:
    CACHES = {"default": {"BACKEND": "django.core.cache.backends.locmem.LocMemCache"}}
API_CACHE_TTL = env.int("API_CACHE_TTL", default=900)  # seconds; public reads
