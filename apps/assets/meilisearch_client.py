"""
Meilisearch integration — self-hosted, free (MIT license, no usage caps).
Only Meilisearch CLOUD (their managed hosting) costs money; running the
open-source binary yourself, via the `meilisearch` docker-compose
service, is genuinely free.

Design: Meilisearch is a REBUILDABLE CACHE, never a source of truth.
Postgres stays authoritative for every field; this module only pushes a
denormalized copy of published+public assets into Meilisearch for fast,
typo-tolerant, prefix-matching search. If Meilisearch is unreachable,
misconfigured, or its disk was wiped (e.g. a free-tier host with no
persistent volume), apps.assets.search falls back to the Postgres engine
automatically — search degrades, it never goes down.

Sync points (mirrors sync_search_vector's call sites exactly):
  - apps/ingestion/services.py: both create and update branches of
    _sync_one(), right after the Postgres search_vector sync.
  - apps/ingestion/management/commands/reseed_assets.py: same spot.
  - apps/assets/views.py: publish/archive actions (index or drop).
  - management command reindex_meilisearch: full rebuild from Postgres —
    run this after any bulk change, or once on boot for a host with no
    persistent disk.
"""

import logging

import meilisearch
from django.conf import settings

logger = logging.getLogger(__name__)

SEARCHABLE_ATTRIBUTES = [
    "title",
    "description",
    "caption",
    "photographer",
    "tags",
    "keywords",
    "location",
    "county",
    "asset_number",
]
FILTERABLE_ATTRIBUTES = [
    "category_id",
    "collection_id",
    "asset_type",
    "county",
    "photographer",
    "year",
    "publication_date_ts",
]
SORTABLE_ATTRIBUTES = ["publication_date_ts", "created_at_ts"]


def _client() -> "meilisearch.Client | None":
    if not settings.MEILISEARCH_URL:
        return None
    return meilisearch.Client(settings.MEILISEARCH_URL, settings.MEILISEARCH_MASTER_KEY or None)


_configured = False  # per-process cache — see _index()


def _index():
    """Every caller goes through here, and every caller needs the index
    to actually exist with primaryKey="id" set explicitly first: with
    3 fields ending in "id" (id, category_id, collection_id), Meilisearch
    can't auto-infer which one is the primary key and silently fails
    every document add until it's set. ensure_index_configured() sets
    it — cached per-process so this isn't an HTTP round-trip per asset."""
    global _configured
    client = _client()
    if client is None:
        return None
    if not _configured:
        _configured = ensure_index_configured()
    return client.index(settings.MEILISEARCH_INDEX)


def ensure_index_configured() -> bool:
    """Create the index and set its searchable/filterable/sortable
    attributes. Idempotent — safe to call on every app boot. Returns
    False (never raises) if Meilisearch isn't configured or unreachable."""
    client = _client()
    if client is None:
        return False
    try:
        client.create_index(settings.MEILISEARCH_INDEX, {"primaryKey": "id"})
    except Exception as exc:  # noqa: BLE001
        # already exists -> fine; anything else -> log and let callers
        # fall back to Postgres rather than crash asset ingestion.
        if "index_already_exists" not in str(exc):
            logger.warning("Meilisearch create_index failed: %s", exc)
            return False
    index = client.index(settings.MEILISEARCH_INDEX)
    try:
        index.update_searchable_attributes(SEARCHABLE_ATTRIBUTES)
        index.update_filterable_attributes(FILTERABLE_ATTRIBUTES)
        index.update_sortable_attributes(SORTABLE_ATTRIBUTES)
        index.update_typo_tolerance(
            {"enabled": True, "minWordSizeForTypos": {"oneTypo": 4, "twoTypos": 8}}
        )
        return True
    except Exception as exc:  # noqa: BLE001
        logger.warning("Meilisearch index configuration failed: %s", exc)
        return False


def _to_document(asset) -> dict:
    """Denormalized document — everything search needs to live, joins
    resolved ahead of time, dates as unix timestamps (Meilisearch sorts/
    filters numerically, not on ISO strings)."""
    import time
    from datetime import date, datetime

    def _as_date(d):
        """Normalize to a real date, however it got onto the instance
        (a plain string can end up here if something bypassed model
        validation — e.g. .create(publication_date="...") in a script).
        Never raises; unrecognized input just yields no date."""
        if isinstance(d, datetime):
            return d.date()
        if isinstance(d, date):
            return d
        if isinstance(d, str):
            from django.utils.dateparse import parse_date

            return parse_date(d)
        return None

    def _ts(d):
        d = _as_date(d)
        return int(time.mktime(d.timetuple())) if d else None

    pub_date = _as_date(asset.publication_date)
    metadata = getattr(asset, "metadata", None)
    return {
        "id": str(asset.id),
        "asset_number": asset.asset_number,
        "title": asset.title,
        "description": asset.description,
        "caption": asset.caption,
        "photographer": asset.photographer,
        "asset_type": asset.asset_type,
        "category_id": str(asset.category_id) if asset.category_id else None,
        "collection_id": str(asset.collection_id) if asset.collection_id else None,
        "tags": [t.name for t in asset.tags.all()],
        "keywords": metadata.keywords if metadata else "",
        "location": metadata.location if metadata else "",
        "county": metadata.county if metadata else "",
        "publication_date": pub_date.isoformat() if pub_date else None,
        "publication_date_ts": _ts(pub_date),
        "year": pub_date.year if pub_date else None,
        "created_at_ts": _ts(asset.created_at) if asset.created_at else None,
    }


def index_asset(asset) -> bool:
    """Add/update a published+public asset in the index, or remove it
    if it no longer qualifies (unpublished, archived, made private).
    Call this after every save — see module docstring for call sites."""
    index = _index()
    if index is None:
        return False
    from .models import DigitalAsset

    qualifies = (
        asset.status == DigitalAsset.Status.PUBLISHED
        and asset.visibility == DigitalAsset.Visibility.PUBLIC
        and asset.deleted_at is None
    )
    try:
        if qualifies:
            index.add_documents([_to_document(asset)])
        else:
            index.delete_document(str(asset.id))
        return True
    except Exception as exc:  # noqa: BLE001
        logger.warning("Meilisearch index_asset failed for %s: %s", asset.id, exc)
        return False


def remove_asset(asset_id) -> bool:
    index = _index()
    if index is None:
        return False
    try:
        index.delete_document(str(asset_id))
        return True
    except Exception as exc:  # noqa: BLE001
        logger.warning("Meilisearch remove_asset failed for %s: %s", asset_id, exc)
        return False


def reindex_all() -> int:
    """Full rebuild from Postgres — the source of truth never changes,
    so this is always safe to re-run. Needed after bulk changes, and on
    boot for any host without a persistent disk for Meilisearch's data."""
    from .models import DigitalAsset

    index = _index()  # configures the index (primaryKey, attributes) as a side effect
    if index is None:
        return 0
    qs = (
        DigitalAsset.objects.filter(
            status=DigitalAsset.Status.PUBLISHED,
            visibility=DigitalAsset.Visibility.PUBLIC,
        )
        .select_related("metadata")
        .prefetch_related("tags")
    )
    docs = [_to_document(a) for a in qs]
    if docs:
        index.add_documents(docs)
    logger.info("Meilisearch reindex: %d documents", len(docs))
    return len(docs)


def search(
    query: str,
    *,
    category_id=None,
    collection_id=None,
    asset_type=None,
    date_from=None,
    date_to=None,
    year=None,
    page: int = 1,
    page_size: int = 20,
) -> tuple[list[str], int] | None:
    """Returns (ordered list of matching asset id strings, total estimated
    hits) or None if Meilisearch isn't usable right now (caller should
    fall back to Postgres). Filtering happens server-side in Meilisearch;
    the caller re-fetches full rows from Postgres by these ids."""
    index = _index()
    if index is None:
        return None

    filters = []
    if category_id:
        filters.append(f'category_id = "{category_id}"')
    if collection_id:
        filters.append(f'collection_id = "{collection_id}"')
    if asset_type:
        filters.append(f'asset_type = "{asset_type}"')
    if year:
        filters.append(f"year = {int(year)}")
    if date_from:
        import time

        ts = int(time.mktime(date_from.timetuple()))
        filters.append(f"publication_date_ts >= {ts}")
    if date_to:
        import time

        ts = int(time.mktime(date_to.timetuple()))
        filters.append(f"publication_date_ts <= {ts}")

    try:
        result = index.search(
            query,
            {
                "filter": filters or None,
                "offset": (page - 1) * page_size,
                "limit": page_size,
            },
        )
        ids = [hit["id"] for hit in result["hits"]]
        total = result.get("estimatedTotalHits", len(ids))
        return ids, total
    except Exception as exc:  # noqa: BLE001
        logger.warning("Meilisearch search failed, falling back to Postgres: %s", exc)
        return None
