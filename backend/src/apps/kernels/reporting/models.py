from __future__ import annotations

import uuid

from django.conf import settings
from django.db import models
from django.utils import timezone

from .enums import ConsumerType, DatasetStatus, FreshnessMode, MaterializationPolicy, RunStatus, ScopeLevel


class ReportDatasetDefinition(models.Model):
    dataset_key = models.CharField(max_length=128, unique=True)
    name = models.CharField(max_length=200)
    description = models.TextField(blank=True, default="")
    domain_owner = models.CharField(max_length=64)
    scope_level = models.CharField(max_length=16, choices=ScopeLevel.choices, default=ScopeLevel.COMPANY)

    required_permissions_json = models.JSONField(default=list)
    filters_schema_json = models.JSONField(default=dict)
    dimensions_schema_json = models.JSONField(default=list)
    measures_schema_json = models.JSONField(default=list)

    freshness_mode = models.CharField(max_length=32, choices=FreshnessMode.choices, default=FreshnessMode.LIVE_ONLY)
    materialization_policy = models.CharField(
        max_length=32,
        choices=MaterializationPolicy.choices,
        default=MaterializationPolicy.LIVE_ONLY,
    )
    export_capabilities_json = models.JSONField(default=list)
    render_hints_json = models.JSONField(default=dict)

    schema_version = models.CharField(max_length=16, default="1.0.0")
    semantic_version = models.CharField(max_length=16, default="1.0.0")
    status = models.CharField(max_length=16, choices=DatasetStatus.choices, default=DatasetStatus.DRAFT)
    is_certified = models.BooleanField(default=False)
    is_enabled = models.BooleanField(default=True)

    created_at = models.DateTimeField(default=timezone.now, editable=False)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        indexes = [
            models.Index(fields=["domain_owner", "is_enabled"], name="ix_rep_ds_owner_enabled"),
            models.Index(fields=["status", "is_enabled"], name="ix_rep_ds_status_enabled"),
        ]

    def __str__(self) -> str:
        return self.dataset_key


class ReportRun(models.Model):
    run_id = models.UUIDField(default=uuid.uuid4, unique=True, editable=False)
    dataset_key = models.CharField(max_length=128, db_index=True)

    requested_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="reporting_runs",
    )
    company = models.ForeignKey(
        "iam.OrgUnit",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="reporting_runs_company",
    )
    branch = models.ForeignKey(
        "iam.OrgUnit",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="reporting_runs_branch",
    )

    filters_json = models.JSONField(default=dict)
    status = models.CharField(max_length=16, choices=RunStatus.choices, default=RunStatus.RUNNING)

    started_at = models.DateTimeField(default=timezone.now, editable=False)
    completed_at = models.DateTimeField(null=True, blank=True)
    duration_ms = models.PositiveIntegerField(null=True, blank=True)
    row_count = models.PositiveIntegerField(default=0)

    result_hash = models.CharField(max_length=64, blank=True, default="")
    warnings_json = models.JSONField(default=list)
    source_summary_json = models.JSONField(default=dict)
    lineage_json = models.JSONField(default=dict)

    consumer_type = models.CharField(max_length=16, choices=ConsumerType.choices, default=ConsumerType.API)
    consumer_ref = models.CharField(max_length=128, blank=True, default="")

    schema_version_used = models.CharField(max_length=16, default="1.0.0")
    semantic_version_used = models.CharField(max_length=16, default="1.0.0")
    error_detail = models.TextField(blank=True, default="")

    created_at = models.DateTimeField(default=timezone.now, editable=False)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        indexes = [
            models.Index(fields=["dataset_key", "created_at"], name="ix_rep_run_ds_created"),
            models.Index(fields=["status", "created_at"], name="ix_rep_run_status_created"),
            models.Index(fields=["company", "branch", "created_at"], name="ix_rep_run_scope_created"),
        ]

    def __str__(self) -> str:
        return f"{self.dataset_key}:{self.run_id}"

