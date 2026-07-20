"""
Catalogue search — Postgres full-text + trigram fuzzy fallback. No
external service (Algolia/Meilisearch/Elasticsearch) needed at this
scale; revisit only if the catalogue grows into the hundreds of
thousands and relevance tuning outgrows what's here.

How a query resolves:
  1. Ranked full-text match against DigitalAsset.search_vector (a
     stored, GIN-indexed column — see sync_search_vector below) OR'd
     with a widen pass across tags/keywords/photographer (join'd
     tables, not in the vector, matched via trigram/icontains).
  2. If that returns nothing, fall back to trigram similarity on
     title — catches typos ("keniatta" -> "Kenyatta") the dictionary-
     based full-text search can't.

search_vector itself must be kept in sync on every asset write — see
sync_search_vector(), called from the ingestion pipeline and
reseed_assets after every _map_fields()+save().
"""

import logging
import time

from django.contrib.postgres.search import (
    SearchQuery,
    SearchRank,
    SearchVector,
    TrigramWordSimilarity,
)
from django.db.models import Q, QuerySet

from .models import DigitalAsset

logger = logging.getLogger(__name__)

FUZZY_THRESHOLD = 0.15  # trigram similarity floor; lower = more forgiving


def build_search_vector() -> SearchVector:
    """Title weighted highest, then caption/description, then photographer.
    Recomputed and stored on every asset save — see sync_search_vector."""
    return (
        SearchVector("title", weight="A", config="english")
        + SearchVector("caption", weight="B", config="english")
        + SearchVector("description", weight="B", config="english")
        + SearchVector("photographer", weight="C", config="english")
    )


def sync_search_vector(asset_id) -> None:
    """Recompute and store one asset's search_vector. Cheap single-row
    UPDATE; call after every asset field change (ingestion, admin edits,
    reseed)."""
    DigitalAsset.objects.filter(pk=asset_id).update(search_vector=build_search_vector())


def search_assets(query: str, queryset: QuerySet) -> tuple[QuerySet, str]:
    """Returns (ranked_queryset, match_type) where match_type is
    'text' or 'fuzzy' — expose this to the frontend so it can show a
    'Showing results for...' correction hint on fuzzy matches."""
    query = (query or "").strip()
    if not query:
        return queryset, "none"

    started = time.monotonic()
    sq = SearchQuery(query, search_type="websearch", config="english")
    ranked = (
        queryset.filter(
            Q(search_vector=sq)
            | Q(tags__name__trigram_similar=query)
            | Q(metadata__keywords__trigram_similar=query)
            | Q(metadata__location__trigram_similar=query)
            | Q(metadata__county__trigram_similar=query)
            | Q(photographer__trigram_similar=query)
        )
        .annotate(rank=SearchRank(build_search_vector(), sq))
        .order_by("-rank", "-created_at")
        .distinct()
    )
    if ranked.exists():
        logger.info(
            "SEARCH q=%r match=text results=%d %.1fms",
            query,
            ranked.count(),
            (time.monotonic() - started) * 1000,
        )
        return ranked, "text"

    # Nothing matched the dictionary/trigram-widened text search — most
    # likely a typo. Fall back to word-level fuzzy similarity: does the
    # query resemble ANY word within the title (not the whole string —
    # a short typo like "Keniata" would score near-zero against a full
    # title compared as one block, so plain TrigramSimilarity misses it).
    fuzzy = (
        queryset.annotate(similarity=TrigramWordSimilarity(query, "title"))
        .filter(similarity__gt=FUZZY_THRESHOLD)
        .order_by("-similarity", "-created_at")
    )
    logger.info(
        "SEARCH q=%r match=fuzzy results=%d %.1fms",
        query,
        fuzzy.count(),
        (time.monotonic() - started) * 1000,
    )
    return fuzzy, "fuzzy"


def suggest_assets(query: str, queryset: QuerySet, limit: int = 8) -> QuerySet:
    """Fast top-N for a live as-you-type dropdown — same engine, small slice."""
    ranked, _ = search_assets(query, queryset)
    return ranked[:limit]
