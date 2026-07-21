#!/usr/bin/env bash
# exit on error
set -o errexit

# Install production dependencies
pip install -r requirements/production.txt

# Collect static files
python manage.py collectstatic --no-input

# Run database migrations
python manage.py migrate

# Rebuild the Meilisearch index from Postgres. Safe to run every deploy:
# it's a full, idempotent rebuild, and does nothing (no error) if
# MEILISEARCH_URL isn't set or the service isn't reachable yet — search
# just runs on the Postgres fallback in that case. Needed on every
# deploy because Meilisearch's free-tier Render instance has no
# persistent disk, so its index is wiped on every restart.
python manage.py reindex_meilisearch
