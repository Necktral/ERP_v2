from __future__ import annotations

from django.db import models


class ScopeLevel(models.TextChoices):
    COMPANY = "COMPANY", "Company"
    BRANCH = "BRANCH", "Branch"


class FreshnessMode(models.TextChoices):
    LIVE_ONLY = "LIVE_ONLY", "Live only"
    CACHE_ALLOWED = "CACHE_ALLOWED", "Cache allowed"
    SNAPSHOT_REQUIRED = "SNAPSHOT_REQUIRED", "Snapshot required"


class MaterializationPolicy(models.TextChoices):
    LIVE_ONLY = "LIVE_ONLY", "Live only"
    CACHE_ALLOWED = "CACHE_ALLOWED", "Cache allowed"
    SNAPSHOT_REQUIRED = "SNAPSHOT_REQUIRED", "Snapshot required"


class DatasetStatus(models.TextChoices):
    DRAFT = "DRAFT", "Draft"
    CERTIFIED = "CERTIFIED", "Certified"
    DEPRECATED = "DEPRECATED", "Deprecated"
    RETIRED = "RETIRED", "Retired"


class RunStatus(models.TextChoices):
    RUNNING = "RUNNING", "Running"
    SUCCEEDED = "SUCCEEDED", "Succeeded"
    FAILED = "FAILED", "Failed"


class ConsumerType(models.TextChoices):
    API = "API", "API"
    DASHBOARD = "DASHBOARD", "Dashboard"
    JOB = "JOB", "Job"
    EXPORT = "EXPORT", "Export"


class ExportFormat(models.TextChoices):
    JSON = "json", "JSON"
    CSV = "csv", "CSV"
    XLSX = "xlsx", "XLSX"

