from __future__ import annotations

from django.contrib import admin

from .models import ReportDatasetDefinition, ReportRun


@admin.register(ReportDatasetDefinition)
class ReportDatasetDefinitionAdmin(admin.ModelAdmin):
    list_display = ("dataset_key", "domain_owner", "status", "is_certified", "is_enabled", "updated_at")
    search_fields = ("dataset_key", "name", "domain_owner")
    list_filter = ("domain_owner", "status", "is_certified", "is_enabled")


@admin.register(ReportRun)
class ReportRunAdmin(admin.ModelAdmin):
    list_display = ("run_id", "dataset_key", "status", "row_count", "duration_ms", "created_at")
    search_fields = ("dataset_key", "run_id")
    list_filter = ("status", "dataset_key", "consumer_type")

