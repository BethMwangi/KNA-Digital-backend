#!/usr/bin/env bash
# One-off admin/seed commands against Supabase (DB + Storage), run through
# the same Docker image as local dev, without touching docker-compose.yml
# or exposing secrets in shell history/logs.
#
# Setup (once):
#   cp .env.supabase.example .env.supabase
#   # fill in real values from Supabase > Database and Supabase > Storage > S3 Connection
#
# Usage:
#   ./scripts/seed_supabase.sh migrate
#   ./scripts/seed_supabase.sh createsuperuser
#   ./scripts/seed_supabase.sh seed_licenses
#   ./scripts/seed_supabase.sh import_local_tiffs --dir /host-tiffs/entertainment --limit 3
#   ./scripts/seed_supabase.sh import_local_tiffs --dir /host-tiffs/entertainment
#   ./scripts/seed_supabase.sh import_local_tiffs --dir /host-tiffs/health
#   ./scripts/seed_supabase.sh seed_asset_prices
#   ./scripts/seed_supabase.sh shell -c "from apps.assets.models import DigitalAsset; print(DigitalAsset.objects.count())"

set -euo pipefail
cd "$(dirname "$0")/.."

ENV_FILE=".env.supabase"
if [ ! -f "$ENV_FILE" ]; then
  echo "Missing $ENV_FILE — copy .env.supabase.example and fill in real values first." >&2
  exit 1
fi

if [ "$#" -eq 0 ]; then
  echo "Usage: $0 <manage.py subcommand> [args...]" >&2
  exit 1
fi

set -a
# shellcheck disable=SC1090
source "$ENV_FILE"
set +a

docker compose run --rm --no-deps \
  -e DJANGO_SETTINGS_MODULE=config.settings.production \
  -e DATABASE_URL \
  -e SUPABASE_S3_ENDPOINT_URL -e SUPABASE_S3_REGION \
  -e SUPABASE_S3_ACCESS_KEY_ID -e SUPABASE_S3_SECRET_ACCESS_KEY \
  -e SUPABASE_PUBLIC_BUCKET -e SUPABASE_PRIVATE_BUCKET \
  -e SECRET_KEY -e JWT_SECRET \
  backend python manage.py "$@"
