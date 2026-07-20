"""
Structured filters for the asset catalogue — date range and a `year`
shorthand for a frontend date picker. Deliberately separate from full-
text search (apps.assets.search): "find images from the 1970s" is a
range filter, not a text query, even though a bare year string happens
to also match via tags today.
"""

import django_filters

from .models import DigitalAsset


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

    class Meta:
        model = DigitalAsset
        fields = ["category", "collection", "asset_type", "publication_date"]

    def filter_year(self, queryset, name, value):
        return queryset.filter(publication_date__year=value)
