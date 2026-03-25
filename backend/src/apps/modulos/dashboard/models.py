from __future__ import annotations

from django.conf import settings
from django.db import models
from django.utils import timezone


class DashboardEmbedGrant(models.Model):
    class Status(models.TextChoices):
        ISSUED = "ISSUED", "Issued"
        REDEEMED = "REDEEMED", "Redeemed"
        EXPIRED = "EXPIRED", "Expired"
        REVOKED = "REVOKED", "Revoked"

    jti = models.CharField(max_length=64, unique=True)
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="dashboard_embed_grants",
    )
    company = models.ForeignKey(
        "iam.OrgUnit",
        on_delete=models.PROTECT,
        related_name="dashboard_embed_grants_company",
    )
    branch = models.ForeignKey(
        "iam.OrgUnit",
        null=True,
        blank=True,
        on_delete=models.PROTECT,
        related_name="dashboard_embed_grants_branch",
    )
    workspace_key = models.CharField(max_length=64)
    perm_codes_json = models.JSONField(default=list)
    status = models.CharField(max_length=16, choices=Status.choices, default=Status.ISSUED)
    expires_at = models.DateTimeField()
    redeemed_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(default=timezone.now, editable=False)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        indexes = [
            models.Index(fields=["status", "expires_at"], name="ix_dash_grant_status_exp"),
            models.Index(fields=["company", "branch", "created_at"], name="ix_dash_grant_scope"),
            models.Index(fields=["workspace_key", "created_at"], name="ix_dash_grant_workspace"),
        ]

    def __str__(self) -> str:
        return f"{self.workspace_key}:{self.jti}"
