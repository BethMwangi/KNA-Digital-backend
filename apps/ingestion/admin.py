from django.contrib import admin

from .models import AssetSyncRecord, LegacyCodeMap, SyncRun


@admin.register(AssetSyncRecord)
class AssetSyncRecordAdmin(admin.ModelAdmin):
    list_display = ["external_refno", "external_id", "asset", "sync_locked", "last_synced_at"]
    list_filter = ["sync_locked"]
    search_fields = ["external_refno", "external_id", "asset__title", "asset__asset_number"]
    readonly_fields = ["external_id", "checksum", "payload", "last_synced_at"]
    list_editable = ["sync_locked"]


@admin.register(LegacyCodeMap)
class LegacyCodeMapAdmin(admin.ModelAdmin):
    list_display = ["item_type", "code", "description", "category", "collection"]
    list_filter = ["item_type"]


@admin.register(SyncRun)
class SyncRunAdmin(admin.ModelAdmin):
    list_display = ["kind", "started_at", "total", "created", "updated", "skipped", "conflicts"]
    readonly_fields = [f.name for f in SyncRun._meta.fields]
