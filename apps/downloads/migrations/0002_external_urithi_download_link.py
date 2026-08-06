from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("downloads", "0001_initial"),
    ]

    operations = [
        migrations.AddField(
            model_name="download",
            name="external_download_status",
            field=models.CharField(blank=True, max_length=50),
        ),
        migrations.AddField(
            model_name="download",
            name="external_download_link",
            field=models.URLField(blank=True, max_length=1000),
        ),
        migrations.AddField(
            model_name="download",
            name="external_download_counts",
            field=models.PositiveIntegerField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name="download",
            name="external_payload",
            field=models.JSONField(blank=True, default=dict),
        ),
        migrations.AddField(
            model_name="download",
            name="external_response",
            field=models.JSONField(blank=True, default=dict),
        ),
        migrations.AddField(
            model_name="download",
            name="external_last_error",
            field=models.TextField(blank=True),
        ),
    ]
