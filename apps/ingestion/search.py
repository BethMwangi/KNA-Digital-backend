"""
Search service — dynamic full-text search across everything the sync maps,
with zero schema changes (query-time SearchVector + ranked results).

Usage in your asset list view:
    from apps.ingestion.search import search_assets
    qs = search_assets(request.query_params.get("q"), base_queryset)

Performance note for production (run once, plain SQL migration; indexes
are additive and don't change table structure):

    CREATE EXTENSION IF NOT EXISTS pg_trgm;
    CREATE INDEX idx_asset_fts ON <digital_asset_table>
      USING GIN (to_tsvector('english',
        coalesce(title,'') || ' ' || coalesce(description,'') || ' ' ||
        coalesce(caption,'')));
    CREATE INDEX idx_asset_title_trgm ON <digital_asset_table>
      USING GIN (title gin_trgm_ops);

Replace <digital_asset_table> with the actual table name
(`python manage.py dbshell` → \\dt to confirm).
"""

from django.contrib.postgres.search import SearchQuery, SearchRank, SearchVector
from django.db.models import Q

ASSET_VECTOR = (
    SearchVector("title", weight="A")
    + SearchVector("caption", weight="B")
    + SearchVector("description", weight="B")
    + SearchVector("metadata__keywords", weight="C")
    + SearchVector("metadata__location", weight="C")
    + SearchVector("photographer", weight="C")
)


def search_assets(query: str | None, queryset):
    if not query:
        return queryset
    sq = SearchQuery(query, search_type="websearch")
    ranked = (
        queryset.annotate(rank=SearchRank(ASSET_VECTOR, sq))
        .filter(Q(rank__gte=0.1) | Q(tags__name__icontains=query))
        .order_by("-rank")
        .distinct()
    )
    return ranked
