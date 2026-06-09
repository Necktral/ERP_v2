"""Detección y gestión de hallazgos de control (Capa 3).

Dos detectores sobre la matriz `SegregationRule`:
- por **concesión** (RBAC): el usuario *posee* ambos permisos de un par tóxico.
- por **ejercicio** (audit log): el usuario *realizó* ambas acciones incompatibles.

Las violaciones se materializan como `ControlFinding` idempotentes (dedup_key) y
quedan auditadas (`CONTROL_FINDING_*`). Reusa
`rbac.selectors.get_effective_permissions_for_scope` y el audit log inmutable.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import timedelta
from typing import Iterable

from django.db import transaction
from django.db.models import Q
from django.utils import timezone

from apps.modulos.audit.models import AuditEvent
from apps.modulos.audit.writer import write_event
from apps.modulos.iam.models import OrgUnit
from apps.modulos.rbac.models import RoleAssignment
from apps.modulos.rbac.selectors import get_effective_permissions_for_scope

from .models import ControlFinding, SegregationRule

DEFAULT_WINDOW_DAYS = 90


@dataclass(frozen=True)
class FindingItem:
    control_code: str
    rule: SegregationRule
    actor_user_id: int | None
    dedup_key: str
    detail: dict = field(default_factory=dict)
    subject_type: str = "USER"
    subject_id: str = ""


def active_rules_for(company: OrgUnit) -> list[SegregationRule]:
    """Reglas activas que aplican a la empresa: las suyas + las globales."""
    return list(
        SegregationRule.objects.filter(is_active=True).filter(Q(company=company) | Q(company__isnull=True))
    )


def _scope_branches(company: OrgUnit) -> list[OrgUnit]:
    return list(OrgUnit.objects.filter(parent=company, unit_type=OrgUnit.UnitType.BRANCH))


def _effective_perms_anywhere(user, company: OrgUnit, branches: list[OrgUnit]) -> set[str]:
    """Permisos efectivos del usuario en cualquier scope de la empresa."""
    perms = set(get_effective_permissions_for_scope(user, company=company, branch=None))
    for branch in branches:
        perms |= set(get_effective_permissions_for_scope(user, company=company, branch=branch))
    return perms


def evaluate_user_segregation(user, company: OrgUnit) -> list[SegregationRule]:
    """Reglas SoD violadas por concesión: el usuario posee ambos permisos."""
    branches = _scope_branches(company)
    perms = _effective_perms_anywhere(user, company, branches)
    if "*" in perms:
        # Superpermiso: por diseño concentra todo; se reporta como violación de
        # toda regla activa (un único actor con poder total es el caso límite).
        return active_rules_for(company)
    violated = []
    for rule in active_rules_for(company):
        if rule.permission_a in perms and rule.permission_b in perms:
            violated.append(rule)
    return violated


def scan_company_segregation(company: OrgUnit) -> list[FindingItem]:
    """Recorre los usuarios con rol activo en la empresa y detecta SOD_GRANT."""
    branches = _scope_branches(company)
    scope_ids = [company.id, *[b.id for b in branches]]
    user_ids = (
        RoleAssignment.objects.filter(org_unit_id__in=scope_ids, is_active=True)
        .values_list("user_id", flat=True)
        .distinct()
    )
    from django.contrib.auth import get_user_model

    User = get_user_model()
    users = User.objects.filter(id__in=list(user_ids))

    items: list[FindingItem] = []
    for user in users:
        for rule in evaluate_user_segregation(user, company):
            items.append(
                FindingItem(
                    control_code=ControlFinding.ControlCode.SOD_GRANT,
                    rule=rule,
                    actor_user_id=user.id,
                    subject_id=str(user.id),
                    dedup_key=f"SOD_GRANT:{rule.code}:{user.id}",
                    detail={
                        "rule_code": rule.code,
                        "permission_a": rule.permission_a,
                        "permission_b": rule.permission_b,
                        "username": getattr(user, "username", ""),
                    },
                )
            )
    return items


def detect_exercised_segregation(company: OrgUnit, *, window_days: int = DEFAULT_WINDOW_DAYS) -> list[FindingItem]:
    """Detecta SOD_EXERCISED: un actor realizó ambas acciones incompatibles.

    Cruza el audit log de la empresa (`partition_key=COMPANY:<id>`) por
    `event_a`/`event_b` de cada regla dentro de la ventana.
    """
    cutoff = timezone.now() - timedelta(days=int(window_days))
    pk = f"COMPANY:{company.id}"
    items: list[FindingItem] = []
    for rule in active_rules_for(company):
        if not (rule.event_a and rule.event_b):
            continue

        def _actors(event_type: str) -> set[int]:
            return set(
                AuditEvent.objects.filter(
                    partition_key=pk,
                    event_type=event_type,
                    timestamp_server__gte=cutoff,
                    actor_user__isnull=False,
                ).values_list("actor_user_id", flat=True)
            )

        both = _actors(rule.event_a) & _actors(rule.event_b)
        for uid in both:
            items.append(
                FindingItem(
                    control_code=ControlFinding.ControlCode.SOD_EXERCISED,
                    rule=rule,
                    actor_user_id=uid,
                    subject_id=str(uid),
                    dedup_key=f"SOD_EXERCISED:{rule.code}:{uid}",
                    detail={
                        "rule_code": rule.code,
                        "event_a": rule.event_a,
                        "event_b": rule.event_b,
                        "window_days": int(window_days),
                    },
                )
            )
    return items


@transaction.atomic
def materialize_findings(
    company: OrgUnit, items: Iterable[FindingItem], *, request=None, actor=None
) -> list[ControlFinding]:
    """Upsert idempotente por dedup_key; audita cada hallazgo nuevo."""
    created: list[ControlFinding] = []
    for item in items:
        finding, was_created = ControlFinding.objects.get_or_create(
            company=company,
            dedup_key=item.dedup_key,
            defaults={
                "control_code": item.control_code,
                "rule": item.rule,
                "severity": item.rule.severity,
                "actor_user_id": item.actor_user_id,
                "subject_type": item.subject_type,
                "subject_id": item.subject_id,
                "detail": item.detail,
                "status": ControlFinding.Status.OPEN,
            },
        )
        if was_created:
            write_event(
                request=request,
                module="CONTROLS",
                event_type="CONTROL_FINDING_RAISED",
                reason_code="OK",
                actor_user=actor,
                subject_type="CONTROL_FINDING",
                subject_id=str(finding.id),
                metadata={
                    "company_id": str(company.id),
                    "control_code": finding.control_code,
                    "rule_code": item.rule.code,
                    "severity": finding.severity,
                },
            )
            created.append(finding)
    return created


def run_detectors(
    company: OrgUnit, *, window_days: int = DEFAULT_WINDOW_DAYS, request=None, actor=None
) -> list[ControlFinding]:
    """Corre ambos detectores y materializa los hallazgos nuevos."""
    items = [*scan_company_segregation(company), *detect_exercised_segregation(company, window_days=window_days)]
    return materialize_findings(company, items, request=request, actor=actor)


@transaction.atomic
def resolve_finding(
    finding: ControlFinding, *, actor, status: str, note: str = "", request=None
) -> ControlFinding:
    """Transiciona un hallazgo (ACK/RESOLVED/DISMISSED) y lo audita."""
    valid = {
        ControlFinding.Status.ACKNOWLEDGED,
        ControlFinding.Status.RESOLVED,
        ControlFinding.Status.DISMISSED,
    }
    if status not in valid:
        raise ValueError(f"Estado de resolución inválido: {status}")

    before = finding.status
    finding.status = status
    finding.resolution_note = note or ""
    if status in (ControlFinding.Status.RESOLVED, ControlFinding.Status.DISMISSED):
        finding.resolved_by = actor
        finding.resolved_at = timezone.now()
    finding.save(update_fields=["status", "resolution_note", "resolved_by", "resolved_at", "updated_at"])

    write_event(
        request=request,
        module="CONTROLS",
        event_type="CONTROL_FINDING_RESOLVED",
        reason_code="OK",
        actor_user=actor,
        subject_type="CONTROL_FINDING",
        subject_id=str(finding.id),
        before_snapshot={"status": before},
        after_snapshot={"status": finding.status},
        metadata={"company_id": str(finding.company_id)},
    )
    return finding
