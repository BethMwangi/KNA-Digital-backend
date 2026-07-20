"""Local development settings."""

from .base import *  # noqa

DEBUG = True
ALLOWED_HOSTS = ["*"]
# base.py already defaults EMAIL_BACKEND to console and only switches to
# real SMTP if EMAIL_BACKEND is explicitly set in .env — so local dev is
# still spam-safe by default, but setting it lets you test real delivery
# (e.g. Gmail) without needing production settings.
