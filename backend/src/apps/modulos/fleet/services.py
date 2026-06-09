"""Servicios de flota (Fase A): registro de activos/conductores, taxonomía de
mantenimiento (materializa plan→estado por activo), lecturas de medidor y documentos.

Sin dinero ni telemetría: sólo datos maestros + cumplimiento. Cada acción de usuario audita.
"""
from __future__ import annotations

from datetime import timedelta
from decimal import Decimal
from typing import Any, Optional

from django.conf import settings
from django.db import transaction
from django.utils import timezone

from apps.modulos.audit.writer import write_event
from apps.modulos.iam.models import OrgUnit

from .models import (
    AssetMaintenanceState,
    Driver,
    DriverAssignment,
    FleetAsset,
    FleetDocument,
    MaintenancePlan,
    MaintenanceRule,
    MaintenanceType,
    TriggerBasis,
)


class FleetError(ValueError):
    """Error de dominio de flota (reason_code en .args[0])."""


def _q2(value) -> Decimal:
    return Decimal(str(value)).quantize(Decimal("0.01"))


# ---------------------------------------------------------------------------
# Activos / conductores
# ---------------------------------------------------------------------------

def upsert_asset(*, request, actor, company: OrgUnit, code: str, **fields) -> FleetAsset:
    with transaction.atomic():
        asset, created = FleetAsset.objects.select_for_update().get_or_create(
            company=company, code=code, defaults=fields
        )
        if not created:
            for k, v in fields.items():
                setattr(asset, k, v)
        asset.full_clean()
        asset.save()
        write_event(
            request=request, module="FLEET", event_type="FLEET_ASSET_UPSERTED",
            reason_code="FLEET_OK", actor_user=actor, subject_type="FLEET_ASSET",
            subject_id=str(asset.id), metadata={"code": code, "asset_type": asset.asset_type, "created": created},
        )
    return asset


def upsert_driver(*, request, actor, company: OrgUnit, full_name: str, **fields) -> Driver:
    employee = fields.pop("employee", None)
    with transaction.atomic():
        license_number = fields.get("license_number") or ""
        existing = None
        if license_number:
            existing = Driver.objects.filter(company=company, license_number=license_number).first()
        driver = existing or Driver(company=company)
        driver.full_name = full_name
        driver.employee = employee
        for k, v in fields.items():
            setattr(driver, k, v)
        driver.full_clean()
        driver.save()
        write_event(
            request=request, module="FLEET", event_type="FLEET_DRIVER_UPSERTED",
            reason_code="FLEET_OK", actor_user=actor, subject_type="FLEET_DRIVER",
            subject_id=str(driver.id), metadata={"full_name": full_name, "license_number": license_number},
        )
    return driver


def assign_driver(*, request, actor, asset: FleetAsset, driver: Driver) -> DriverAssignment:
    with transaction.atomic():
        DriverAssignment.objects.filter(asset=asset, is_active=True).update(
            is_active=False, released_at=timezone.now()
        )
        asg = DriverAssignment.objects.create(asset=asset, driver=driver, is_active=True)
        write_event(
            request=request, module="FLEET", event_type="FLEET_DRIVER_ASSIGNED",
            reason_code="FLEET_OK", actor_user=actor, subject_type="FLEET_ASSET",
            subject_id=str(asset.id), metadata={"driver_id": driver.id, "assignment_id": asg.id},
        )
    return asg


def record_meter_reading(
    *, request, actor, asset: FleetAsset, odometer_km=None, hourmeter=None
) -> dict[str, Any]:
    """Actualiza el medidor. Un salto grande o una lectura DECRECIENTE no avanza el
    medidor oficial y marca la lectura como no verificada (no dispara reglas).

    FL-01: una lectura decreciente antes se descartaba en silencio con verified=True.
    FL-02: el horómetro ahora también tiene guarda de salto; los umbrales son
    configurables (settings FLEET_ODOMETER_JUMP_KM / FLEET_HOURMETER_JUMP_HOURS).
    """
    odo_jump = Decimal(str(getattr(settings, "FLEET_ODOMETER_JUMP_KM", 500)))
    hour_jump = Decimal(str(getattr(settings, "FLEET_HOURMETER_JUMP_HOURS", 100)))
    verified = True
    update_fields: list[str] = []
    if odometer_km is not None:
        odometer_km = _q2(odometer_km)
        prev = asset.current_odometer_km
        if prev and prev > 0 and (odometer_km - prev) > odo_jump:
            verified = False  # salto sospechoso: no dispara reglas
        elif odometer_km < prev:
            verified = False  # FL-01: lectura decreciente sospechosa (no retrocede el oficial)
        else:
            asset.current_odometer_km = odometer_km
            update_fields.append("current_odometer_km")
    if hourmeter is not None:
        hourmeter = _q2(hourmeter)
        prevh = asset.current_hourmeter
        if prevh and prevh > 0 and (hourmeter - prevh) > hour_jump:
            verified = False  # FL-02: salto de horómetro sospechoso
        elif hourmeter < prevh:
            verified = False  # FL-01: horómetro decreciente sospechoso
        else:
            asset.current_hourmeter = hourmeter
            update_fields.append("current_hourmeter")
    if update_fields:
        asset.save(update_fields=[*update_fields, "updated_at"])
    write_event(
        request=request, module="FLEET", event_type="FLEET_METER_RECORDED",
        reason_code="FLEET_OK", actor_user=actor, subject_type="FLEET_ASSET",
        subject_id=str(asset.id),
        metadata={"odometer_km": str(odometer_km) if odometer_km is not None else None,
                  "hourmeter": str(hourmeter) if hourmeter is not None else None, "verified": verified},
    )
    return {
        "verified": verified,
        "current_odometer_km": str(asset.current_odometer_km),
        "current_hourmeter": str(asset.current_hourmeter),
    }


# ---------------------------------------------------------------------------
# Taxonomía de mantenimiento
# ---------------------------------------------------------------------------

def upsert_maintenance_type(*, company: OrgUnit, code: str, name: str, **fields) -> MaintenanceType:
    obj, _ = MaintenanceType.objects.update_or_create(
        company=company, code=code, defaults={"name": name, **fields}
    )
    return obj


def create_plan(*, company: OrgUnit, name: str, asset_class: str = "") -> MaintenancePlan:
    return MaintenancePlan.objects.create(company=company, name=name, asset_class=asset_class)


def add_rule(
    *, plan: MaintenancePlan, maintenance_type: MaintenanceType, trigger_basis: str,
    interval_km=None, interval_hours=None, interval_days=None,
    severity_factor=Decimal("1.00"), recommended_action: str = "",
) -> MaintenanceRule:
    return MaintenanceRule.objects.create(
        plan=plan, maintenance_type=maintenance_type, trigger_basis=trigger_basis,
        interval_km=interval_km, interval_hours=interval_hours, interval_days=interval_days,
        severity_factor=severity_factor, recommended_action=recommended_action,
    )


def _next_due_for_rule(asset: FleetAsset, rule: MaintenanceRule) -> dict[str, Any]:
    """Calcula el próximo vencimiento desde el medidor/fecha actual del activo (intervalo/severidad)."""
    sev = rule.severity_factor or Decimal("1.00")
    out: dict[str, Any] = {"next_due_km": None, "next_due_hours": None, "next_due_date": None}
    if rule.trigger_basis == TriggerBasis.KM and rule.interval_km:
        out["next_due_km"] = _q2(asset.current_odometer_km + (rule.interval_km / sev))
    elif rule.trigger_basis == TriggerBasis.HOURS and rule.interval_hours:
        out["next_due_hours"] = _q2(asset.current_hourmeter + (rule.interval_hours / sev))
    elif rule.trigger_basis == TriggerBasis.TIME and rule.interval_days:
        days = int(rule.interval_days / sev) if sev else int(rule.interval_days)
        out["next_due_date"] = timezone.localdate() + timedelta(days=max(days, 1))
    return out


def apply_plan_to_asset(*, asset: FleetAsset, plan: MaintenancePlan) -> list[AssetMaintenanceState]:
    """Materializa cada regla del plan como estado de mantenimiento del activo (próximo vencimiento)."""
    states: list[AssetMaintenanceState] = []
    with transaction.atomic():
        for rule in plan.rules.filter(is_active=True):
            due = _next_due_for_rule(asset, rule)
            # FL-03: al re-aplicar el plan solo se refrescan los umbrales de vencimiento;
            # NO se resetea `is_due`/`last_flagged_at` (antes ocultaba un mantenimiento ya
            # marcado como vencido). El estado inicial se fija solo al CREAR.
            state, _ = AssetMaintenanceState.objects.update_or_create(
                asset=asset, rule=rule,
                defaults={**due},
                create_defaults={**due, "is_due": False, "last_flagged_at": None},
            )
            states.append(state)
    return states


# ---------------------------------------------------------------------------
# Documentación
# ---------------------------------------------------------------------------

def register_document(
    *, request, actor, company: OrgUnit, doc_type: str,
    asset: Optional[FleetAsset] = None, driver: Optional[Driver] = None, **fields
) -> FleetDocument:
    if bool(asset) == bool(driver):
        raise FleetError("FLEET_DOCUMENT_ONE_OWNER")
    with transaction.atomic():
        doc = FleetDocument(company=company, asset=asset, driver=driver, doc_type=doc_type, **fields)
        doc.full_clean()
        doc.save()
        write_event(
            request=request, module="FLEET", event_type="FLEET_DOCUMENT_REGISTERED",
            reason_code="FLEET_OK", actor_user=actor, subject_type="FLEET_DOCUMENT",
            subject_id=str(doc.id),
            metadata={"doc_type": doc_type, "asset_id": asset.id if asset else None,
                      "driver_id": driver.id if driver else None,
                      "expiry_date": doc.expiry_date.isoformat() if doc.expiry_date else None},
        )
    return doc
