# Search feature: full-text (search_vector, GIN) + trigram fuzzy matching
# for typo tolerance. TrigramExtension must run before any opclasses=
# ["gin_trgm_ops"] index or their creation fails on a fresh database.

import django.contrib.postgres.indexes
import django.contrib.postgres.search
from django.contrib.postgres.operations import TrigramExtension
from django.db import migrations


class Migration(migrations.Migration):

    dependencies = [
        ("assets", "0006_assetmetadata_date_digitized"),
    ]

    operations = [
        TrigramExtension(),
        migrations.AddField(
            model_name="digitalasset",
            name="search_vector",
            field=django.contrib.postgres.search.SearchVectorField(
                blank=True, editable=False, null=True
            ),
        ),
        migrations.AddIndex(
            model_name="assetmetadata",
            index=django.contrib.postgres.indexes.GinIndex(
                fields=["keywords"], name="assetmeta_kw_trgm", opclasses=["gin_trgm_ops"]
            ),
        ),
        migrations.AddIndex(
            model_name="digitalasset",
            index=django.contrib.postgres.indexes.GinIndex(
                fields=["search_vector"], name="asset_search_vector_gin"
            ),
        ),
        migrations.AddIndex(
            model_name="digitalasset",
            index=django.contrib.postgres.indexes.GinIndex(
                fields=["title"], name="asset_title_trgm_gin", opclasses=["gin_trgm_ops"]
            ),
        ),
        migrations.AddIndex(
            model_name="tag",
            index=django.contrib.postgres.indexes.GinIndex(
                fields=["name"], name="tag_name_trgm_gin", opclasses=["gin_trgm_ops"]
            ),
        ),
    ]
