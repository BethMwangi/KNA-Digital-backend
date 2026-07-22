"""
Structured filters for the asset catalogue.

Every categorical filter (category, collection, asset_type, county,
photographer) accepts a COMMA-SEPARATED list for multi-select ("show me
Kiambu OR Nairobi") and combines with every other filter via AND
("Kiambu county AND year 1979"). A single value with no comma still
works exactly as before — this is a strict superset, not a breaking
change: ?county=Kiambu behaves identically to ?county=Kiambu,Nairobi
with one fewer element.

date_from/date_to/year are deliberately separate from full-text search
(apps.assets.search): "find images from the 1970s" is a range filter,
not a text query, even though a bare year string happens to also match
via tags today.
"""

import django_filters

from .models import DigitalAsset


class CharInFilter(django_filters.BaseCSVFilter, django_filters.CharFilter):
    """?field=a,b,c -> WHERE field IN (a, b, c). A single value (no
    comma) degrades to a normal exact match — fully backward compatible."""


class DigitalAssetFilter(django_filters.FilterSet):
    date_from = django_filters.DateFilter(
        field_name="publication_date",
        lookup_expr="gte",
        help_text="Only assets published on/after this date (YYYY-MM-DD).",
    )
    date_to = django_filters.DateFilter(
        field_name="publication_date",
        lookup_expr="lte",
        help_text="Only assets published on/before this date (YYYY-MM-DD).",
    )
    year = django_filters.NumberFilter(
        method="filter_year",
        help_text="Shorthand for date_from/date_to spanning one year.",
    )
    category = CharInFilter(
        field_name="category_id",
        lookup_expr="in",
        help_text="One or more category ids, comma-separated.",
    )
    collection = CharInFilter(
        field_name="collection_id",
        lookup_expr="in",
        help_text="One or more collection ids, comma-separated.",
    )
    asset_type = CharInFilter(
        field_name="asset_type",
        lookup_expr="in",
        help_text="One or more asset types, comma-separated.",
    )
    county = CharInFilter(
        field_name="metadata__county",
        lookup_expr="in",
        help_text="One or more county names, comma-separated, e.g. Kiambu,Nairobi. "
        "Values must match /api/v1/assets/counties/ exactly (case-sensitive).",
    )
    photographer = CharInFilter(
        field_name="photographer",
        lookup_expr="in",
        help_text="One or more photographer names, comma-separated.",
    )

    class Meta:
        model = DigitalAsset
        fields = ["publication_date"]

    def filter_year(self, queryset, name, value):
        return queryset.filter(publication_date__year=value)
