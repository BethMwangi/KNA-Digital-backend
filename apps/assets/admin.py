from django.contrib import admin

from .models import AssetMetadata, AssetVariant, Category, Collection, DigitalAsset, Tag


class AssetMetadataInline(admin.StackedInline):
    model = AssetMetadata
    extra = 0


class AssetVariantInline(admin.TabularInline):
    model = AssetVariant
    extra = 0


@admin.register(DigitalAsset)
class DigitalAssetAdmin(admin.ModelAdmin):
    list_display = ["asset_number", "title", "asset_type", "status", "visibility", "created_at"]
    list_filter = ["status", "visibility", "asset_type", "category"]
    search_fields = ["asset_number", "title", "description"]
    readonly_fields = ["id", "created_at", "updated_at"]
    inlines = [AssetMetadataInline, AssetVariantInline]


@admin.register(Category)
class CategoryAdmin(admin.ModelAdmin):
    list_display = ["name", "slug"]
    prepopulated_fields = {"slug": ("name",)}


@admin.register(Collection)
class CollectionAdmin(admin.ModelAdmin):
    list_display = ["name", "slug"]
    prepopulated_fields = {"slug": ("name",)}


@admin.register(Tag)
class TagAdmin(admin.ModelAdmin):
    list_display = ["name", "slug"]
    prepopulated_fields = {"slug": ("name",)}
