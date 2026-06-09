"""Puente Costo de finca → Contabilidad (#1 Fase 2).

Reclasifica el **costo real por finca** (mano de obra de la asistencia de campo +
insumos) a un asiento por finca, best-effort (igual que nómina/facturación): emite el
outbox `FincaCostAccrued` y lo enlaza al motor de posting, que genera un `JournalDraft`
balanceado (DÉBITO costo-cultivo-por-finca / CRÉDITO costos-aplicados contra). **Nunca
bloquea.** No capitaliza a activo: el total de Resultados no cambia, el costo queda
visible por finca. Dependencia `modulos.finca → {modulos.integration, kernels.accounting}`.
"""
from __future__ import annotations

import logging
from decimal import Decimal
from typing import Any

from apps.modulos.audit.writer import write_event
from apps.modulos.iam.models import OrgUnit
from apps.modulos.integration.models import OutboxEvent
from apps.modulos.integration.services import publish_outbox_event

from .field_link import _company_of, finca_real_cost_summary

logger = logging.getLogger(__name__)


def post_finca_cost_to_accounting(
    *, request, actor, finca: OrgUnit, season: str | None = None, **filters
) -> dict[str, Any]:
    """Emite el asiento de reclasificación del costo real de una finca (best-effort)."""
    # F-03: validar que el padre sea realmente una COMPANY (igual que field_link),
    # para no postear con una company equivocada si la jerarquía difiere.
    company = _company_of(finca)
    summary = finca_real_cost_summary(finca, season=season, **filters)
    total_cost = Decimal(summary["total_cost"])

    if total_cost <= Decimal("0.00") or company is None:
        write_event(
            request=request,
            module="FINCA",
            event_type="FINCA_COST_POSTED",
            reason_code="FINCA_OK",
            actor_user=actor,
            subject_type="FINCA",
            subject_id=str(finca.id),
            metadata={"finca_id": finca.id, "total_cost": summary["total_cost"], "link_status": "SKIPPED"},
        )
        return {"outbox_event_id": None, "journal_draft_id": None, "link_status": "SKIPPED",
                "total_cost": summary["total_cost"]}

    # F-02: idempotencia por (finca, season). Re-ejecutar no debe emitir un segundo
    # FincaCostAccrued (el kernel de contabilidad dedupe por outbox_event_id, así que
    # el doble-asiento solo vendría de emitir un segundo evento para la misma finca/temporada).
    existing = (
        OutboxEvent.objects.filter(
            source_module="FINCA",
            event_type="FincaCostAccrued",
            company=company,
            payload__data__finca_id=finca.id,
            payload__data__season=season or "",
        )
        .order_by("id")
        .first()
    )
    if existing is not None:
        return {
            "outbox_event_id": str(existing.event_id),
            "journal_draft_id": None,
            "link_status": "ALREADY_POSTED",
            "total_cost": summary["total_cost"],
        }

    payload = {
        "finca_id": finca.id,
        "finca_name": finca.name,
        "zona": summary["zona"],
        "season": season or "",
        "total_cost": summary["total_cost"],
        "real_labor_cost": summary["real_labor_cost"],
        "insumo_cost": summary["insumo_cost"],
    }
    outbox = publish_outbox_event(
        source_module="FINCA",
        event_type="FincaCostAccrued",
        payload=payload,
        company=company,
        branch=finca,
        actor_user=actor,
        request=request,
    )

    journal_draft_id = None
    link_status = "SKIPPED"
    try:
        from apps.kernels.accounting.services import (
            apply_accounting_link_to_outbox_event,
            link_operational_event_to_accounting,
        )

        link = link_operational_event_to_accounting(outbox_event=outbox, actor_user=actor)
        apply_accounting_link_to_outbox_event(outbox_event=outbox, link=link)
        journal_draft_id = link.journal_draft_id
        link_status = link.status
    except (ImportError, AttributeError, RuntimeError, ValueError, KeyError, TypeError):
        # Best-effort: la contabilidad nunca bloquea el registro de finca.
        # F-06: dejar rastro del fallo (antes quedaba solo en link_status, poco visible).
        logger.exception(
            "finca_cost_accounting_link_failed",
            extra={"finca_id": finca.id, "season": season or "", "event_id": str(getattr(outbox, "event_id", ""))},
        )
        link_status = "FAILED"

    write_event(
        request=request,
        module="FINCA",
        event_type="FINCA_COST_POSTED",
        reason_code="FINCA_OK",
        actor_user=actor,
        subject_type="FINCA",
        subject_id=str(finca.id),
        metadata={
            "finca_id": finca.id,
            "total_cost": summary["total_cost"],
            "journal_draft_id": journal_draft_id,
            "link_status": link_status,
        },
    )
    return {
        "outbox_event_id": str(outbox.event_id),
        "journal_draft_id": journal_draft_id,
        "link_status": link_status,
        "total_cost": summary["total_cost"],
    }
