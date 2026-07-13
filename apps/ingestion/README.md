# apps/ingestion — Legacy KNA Archive Sync

Run the following commands to ingest the data

```bash
python manage.py makemigrations ingestion
python manage.py migrate
python manage.py sync_legacy --categories data/categories.json
python manage.py sync_legacy --images data/images.json
```

Re-running is always safe: unchanged records are skipped (checksum),
edited records are re-mapped, curated records (sync_locked=True in admin)
are protected and conflicts logged.

Env vars for the future API + external downloads:
```
LEGACY_ARCHIVE_BASE_URL=
LEGACY_ARCHIVE_API_KEY=
```

Mapping decisions (ADR-style):
- main_category → Collection; sub_category → Category. The legacy pairing
  is per-image and inconsistent (sub 'Presidential' appears under multiple
  mains), so no parent/child tree is forced.
- image_id → AssetSyncRecord.external_id (dedupe/upsert key).
- image_refno → DigitalAsset.asset_number (natural business key).
- Unmapped source fields live verbatim in AssetSyncRecord.payload (JSONB).
- Thumbnails from the source are pre-watermarked: small → 'thumbnail'
  variant (listing grid), large → 'preview' variant (detail page).
- Purchased originals are NOT stored by us: after payment, downloads/views
  calls ingestion.download_client.ExternalArchiveClient.get_download_url().
