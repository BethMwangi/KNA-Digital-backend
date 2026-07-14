"""
Groups /docs by Django app instead of URL path segment.

drf-spectacular's default tagging splits on the first URL path component,
so /api/v1/auth/..., /api/v1/users/... and /api/v1/admin/users/... (all
apps.accounts) land as three separate groups, and each router-registered
resource under apps.assets (categories, collections, tags, assets) gets
its own group too. This derives the tag from the view's app instead, so
the docs mirror the apps/ folder layout — one section per app.
"""

from drf_spectacular.openapi import AutoSchema


class AppGroupedAutoSchema(AutoSchema):
    def get_tags(self) -> list[str]:
        module_parts = self.view.__class__.__module__.split(".")
        if len(module_parts) >= 2 and module_parts[0] == "apps":
            return [module_parts[1].replace("_", " ").title()]
        return super().get_tags()
