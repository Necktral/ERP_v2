"""Simulación funcional end-to-end de la columna económica (spine).

Conduce el ciclo de negocio completo por **etapas**, de forma idempotente, y emite un
reporte JSON por etapa (estado, métricas, refs). Es el corazón "funcional" de la
simulación; la capa de carga (k6) y el monitoreo (Grafana) viven en `simulacion/`.

Etapas: org/RBAC → parties/HR → inventario → facturación (contado+crédito) →
portfolio → nómina (config→período→planilla→aprobar SoD→pagar→cierre) → contabilidad
(approve/post drafts SoD → cierre fiscal).

Uso:
    python manage.py run_business_simulation --tag demo1 --report /tmp/sim.json

Idempotente: re-ejecutar con el mismo `--tag` reusa el escenario (códigos estables).
Cada etapa se aísla: si una falla, se registra y la simulación continúa (best-effort),
de modo que el reporte muestre exactamente hasta dónde llegó el spine.
"""
from __future__ import annotations

import json
import time
import uuid
from decimal import Decimal
from typing import Any, Callable

from django.core.management.base import BaseCommand


class _Req:
    """Request sintético para los services (scope company/branch sin HTTP)."""

    def __init__(self, *, user=None, company=None, branch=None) -> None:
        self.user = user
        self.company = company
        self.branch = branch
        self.data: dict[str, Any] = {}
        self.META: dict[str, Any] = {}
        self._request = None
        self.ctx = None
        self.request_id = f"sim-{uuid.uuid4().hex[:8]}"
        self.path = "/sim"
        self.method = "POST"
        self.headers: dict[str, str] = {}


class Command(BaseCommand):
    help = "Simulación funcional end-to-end de la columna económica (spine)."

    def add_arguments(self, parser):
        parser.add_argument("--tag", type=str, default="sim", help="Etiqueta estable del escenario (idempotencia).")
        parser.add_argument("--report", type=str, default="", help="Ruta para escribir el reporte JSON.")
        parser.add_argument("--workers", type=int, default=3, help="Nº de empleados de planilla a simular.")

    def handle(self, *args, **options):
        tag = str(options["tag"]).strip() or "sim"
        report: dict[str, Any] = {
            "tag": tag,
            "started_at": time.time(),
            "stages": [],
        }
        ctx: dict[str, Any] = {"tag": tag, "workers": int(options["workers"])}

        stages: list[tuple[str, Callable[[dict], dict]]] = [
            ("org_rbac", self._stage_org_rbac),
            ("parties_hr", self._stage_parties_hr),
            ("inventory", self._stage_inventory),
            ("billing", self._stage_billing),
            ("portfolio", self._stage_portfolio),
            ("payroll", self._stage_payroll),
            ("accounting", self._stage_accounting),
        ]

        for name, fn in stages:
            t0 = time.time()
            entry: dict[str, Any] = {"stage": name}
            try:
                entry["data"] = fn(ctx) or {}
                entry["status"] = "OK"
            except Exception as exc:  # noqa: BLE001 — aislar cada etapa para reportar hasta dónde llegó
                entry["status"] = "FAILED"
                entry["error"] = f"{type(exc).__name__}: {exc}"
            entry["ms"] = round((time.time() - t0) * 1000, 1)
            report["stages"].append(entry)
            flag = self.style.SUCCESS("OK") if entry["status"] == "OK" else self.style.ERROR("FAILED")
            self.stdout.write(f"[{name}] {flag} ({entry['ms']} ms)" + (f" — {entry.get('error','')}" if entry["status"] == "FAILED" else ""))

        report["finished_at"] = time.time()
        report["ok"] = all(s["status"] == "OK" for s in report["stages"])
        if options["report"]:
            with open(options["report"], "w", encoding="utf-8") as fh:
                json.dump(report, fh, indent=2, ensure_ascii=False)
            self.stdout.write(f"Reporte: {options['report']}")
        self.stdout.write(self.style.SUCCESS("SPINE OK") if report["ok"] else self.style.WARNING("SPINE PARCIAL"))

    # ------------------------------------------------------------------ #
    # Etapa 1 — Org & RBAC
    # ------------------------------------------------------------------ #
    def _stage_org_rbac(self, ctx: dict) -> dict:
        from django.contrib.auth import get_user_model

        from apps.modulos.iam.models import OrgUnit, UserMembership
        from apps.modulos.rbac.models import Permission, Role, RoleAssignment, RolePermission

        tag = ctx["tag"]
        User = get_user_model()
        holding, _ = OrgUnit.objects.get_or_create(
            unit_type=OrgUnit.UnitType.HOLDING, code=f"SIMH-{tag}", defaults={"name": f"Sim Holding {tag}"}
        )
        company, _ = OrgUnit.objects.get_or_create(
            unit_type=OrgUnit.UnitType.COMPANY, code=f"SIMC-{tag}", parent=holding,
            defaults={"name": f"Sim Company {tag}"},
        )
        branch, _ = OrgUnit.objects.get_or_create(
            unit_type=OrgUnit.UnitType.BRANCH, code=f"SIMB-{tag}", parent=company,
            defaults={"name": f"Sim Branch {tag}"},
        )
        admin, created = User.objects.get_or_create(username=f"sim_admin_{tag}")
        if created:
            admin.set_password("sim-pass-x")
            admin.is_active = True
            admin.save()
        checker, c2 = User.objects.get_or_create(username=f"sim_checker_{tag}")
        if c2:
            checker.set_password("sim-pass-x")
            checker.is_active = True
            checker.save()

        for u in (admin, checker):
            UserMembership.objects.get_or_create(user=u, org_unit=company, defaults={"is_active": True})
            UserMembership.objects.get_or_create(user=u, org_unit=branch, defaults={"is_active": True})

        # Rol amplio para la simulación (todos los permisos que las etapas usan).
        role, _ = Role.objects.get_or_create(name=f"sim_role_{tag}", defaults={"is_active": True})
        perms = [
            "inventory.warehouse.create", "inventory.item.create", "inventory.movement.receive",
            "inventory.movement.issue", "nomina.period.approve", "billing.doc.issue",
        ]
        for code in perms:
            p, _ = Permission.objects.get_or_create(code=code, defaults={"description": code, "is_active": True})
            RolePermission.objects.get_or_create(role=role, permission=p)
        for u in (admin, checker):
            RoleAssignment.objects.get_or_create(user=u, role=role, org_unit=company, defaults={"is_active": True})
            RoleAssignment.objects.get_or_create(user=u, role=role, org_unit=branch, defaults={"is_active": True})

        ctx.update(company=company, branch=branch, admin=admin, checker=checker)
        ctx["req"] = _Req(user=admin, company=company, branch=branch)
        return {"company_id": company.id, "branch_id": branch.id, "admin": admin.username, "checker": checker.username}

    # ------------------------------------------------------------------ #
    # Etapa 2 — Parties & HR
    # ------------------------------------------------------------------ #
    def _stage_parties_hr(self, ctx: dict) -> dict:
        from apps.modulos.hr.models import Employee
        from apps.modulos.parties.models import Party

        company = ctx["company"]
        tag = ctx["tag"]
        # national_id se normaliza (strip+upper) al guardar → usar ya normalizado para
        # que get_or_create reencuentre la party en re-ejecuciones (idempotencia).
        customer, _ = Party.objects.get_or_create(
            company=company, national_id=f"SIMCUST-{tag}".upper(),
            defaults={"display_name": f"Cliente Sim {tag}", "party_type": Party.PartyType.NATURAL},
        )
        employees = []
        for i in range(int(ctx["workers"])):
            emp, _ = Employee.objects.get_or_create(
                company=company, employee_code=f"SIME{i}-{tag}",
                defaults={"first_name": f"Trab{i}", "last_name": "Sim", "is_active": True},
            )
            employees.append(emp)
        ctx.update(customer=customer, employees=employees)
        return {"customer_id": customer.id, "employees": len(employees)}

    # ------------------------------------------------------------------ #
    # Etapa 3 — Inventario (bodega + ítem + recepción)
    # ------------------------------------------------------------------ #
    def _stage_inventory(self, ctx: dict) -> dict:
        from apps.kernels.inventarios.models import InventoryItem, Warehouse
        from apps.kernels.inventarios.services import post_receive

        company, branch, req = ctx["company"], ctx["branch"], ctx["req"]
        tag = ctx["tag"]
        wh, _ = Warehouse.objects.get_or_create(company=company, branch=branch, code=f"SIMW-{tag}", defaults={"name": "Sim Bodega"})
        item, _ = InventoryItem.objects.get_or_create(company=company, sku=f"SIM-SKU-{tag}", defaults={"name": "Producto Sim"})

        res = post_receive(
            request=req, actor=ctx["admin"], warehouse_id=wh.id, item_id=item.id,
            qty=Decimal("100"), unit_cost=Decimal("25.00"),
            idempotency_key=f"sim-recv:{tag}", note="seed sim",
        )
        ctx.update(warehouse=wh, item=item)
        return {"warehouse_id": wh.id, "item_id": item.id, "qty_on_hand": str(res.qty_on_hand), "avg_cost": str(res.avg_cost)}

    # ------------------------------------------------------------------ #
    # Etapa 4 — Facturación (contado: draft → issue con baja de inventario)
    # ------------------------------------------------------------------ #
    def _stage_billing(self, ctx: dict) -> dict:
        from apps.kernels.facturacion.models import DocType
        from apps.kernels.facturacion.services import create_draft, issue_doc

        req = ctx["req"]
        tag = ctx["tag"]
        draft = create_draft(
            request=req, actor=ctx["admin"], doc_type=DocType.INVOICE, series="A", currency="NIO",
            customer_name="Consumidor Final", customer_ref="", is_fiscal=False,
            lines=[{
                "description": "Venta Sim", "quantity": Decimal("5"), "unit_price": Decimal("40.00"),
                "tax_rate": Decimal("0"), "inventory_item_id": ctx["item"].id, "warehouse_id": ctx["warehouse"].id,
            }],
            idempotency_key=f"sim-sale:{tag}", source_module="SIMULATION", source_type="SALE", source_id=tag,
        )
        out = issue_doc(request=req, actor=ctx["admin"], doc_id=draft.doc_id, apply_inventory=True,
                        idempotency_key=f"sim-issue:{tag}")
        ctx["billing_doc_id"] = draft.doc_id
        return {"doc_id": draft.doc_id, "number": out.get("number"), "issued": out.get("ok", False)}

    # ------------------------------------------------------------------ #
    # Etapa 5 — Portfolio (CxC + pago + asignación)
    # ------------------------------------------------------------------ #
    def _stage_portfolio(self, ctx: dict) -> dict:
        from datetime import timedelta

        from django.utils import timezone

        from apps.kernels.portfolio.services import create_receivable

        company, branch = ctx["company"], ctx["branch"]
        today = timezone.localdate()
        rec = create_receivable(
            company=company, branch=branch, party=ctx["customer"],
            reference_type="SIMULATION", reference_id=1,
            principal_amount=Decimal("1000.00"), currency="NIO",
            issue_date=today, due_date=today + timedelta(days=30), created_by=ctx["admin"],
        )
        ctx["receivable_id"] = rec.id
        return {"receivable_id": str(rec.obligation_id), "outstanding": str(rec.outstanding_amount)}

    # ------------------------------------------------------------------ #
    # Etapa 6 — Nómina (config → período → planilla → entries → compute → aprobar SoD → pagar)
    # ------------------------------------------------------------------ #
    def _stage_payroll(self, ctx: dict) -> dict:
        from datetime import date

        from apps.kernels.nomina.models import PayrollEntry, PayrollPeriod, PayrollSheet, PeriodType, SalaryType
        from apps.kernels.nomina.period_sod import approve_period, request_period_approval
        from apps.kernels.nomina.payroll_payments import register_payroll_payment
        from apps.kernels.nomina.services import compute_entry, create_default_nicaragua_config

        req, company = ctx["req"], ctx["company"]
        create_default_nicaragua_config(request=req, actor=ctx["admin"], company=company, fiscal_year=2026)
        # Período idempotente por (company, year, month, type).
        period, _ = PayrollPeriod.objects.get_or_create(
            company=company, year=2026, month=6, period_type=PeriodType.FIRST_HALF,
            defaults={"start_date": date(2026, 6, 1), "end_date": date(2026, 6, 15), "working_days": 15},
        )
        sheet, _ = PayrollSheet.objects.get_or_create(period=period, sheet_name="Sim Planilla", defaults={"has_inss": True})
        net_total = Decimal("0.00")
        for emp in ctx["employees"]:
            entry, _ = PayrollEntry.objects.get_or_create(
                sheet=sheet, employee=emp,
                defaults={
                    "full_name": f"{emp.first_name} {emp.last_name}", "has_inss": True,
                    "salary_type": SalaryType.MONTHLY, "base_salary_nio": Decimal("9000.00"),
                    "days_in_period": 15, "days_worked": Decimal("15.00"),
                },
            )
            compute_entry(entry=entry)
            net_total += entry.net_to_pay

        # Aprobación SoD (maker=admin, checker=checker) — solo si aún es aprobable.
        approved = False
        from apps.kernels.nomina.models import PeriodStatus
        if period.status in (PeriodStatus.DRAFT, PeriodStatus.IN_REVIEW):
            approval = request_period_approval(request=req, actor=ctx["admin"], period=period,
                                               idempotency_key=f"sim-approve:{ctx['tag']}")
            checker_req = _Req(user=ctx["checker"], company=company, branch=ctx["branch"])
            approve_period(request=checker_req, approver=ctx["checker"], approval=approval)
            approved = True
            period.refresh_from_db()

        paid = 0
        for entry in sheet.entries.all():
            if entry.net_to_pay and entry.net_to_pay > 0 and not entry.payments.exists():
                register_payroll_payment(
                    request=req, actor=ctx["admin"], entry=entry, payment_method="CASH",
                    amount=entry.net_to_pay, reference=f"sim-pay:{entry.id}",
                )
                paid += 1
        return {"period_id": period.id, "status": period.status, "approved": approved,
                "entries": sheet.entries.count(), "net_total": str(net_total), "paid": paid}

    # ------------------------------------------------------------------ #
    # Etapa 7 — Contabilidad (dispatch outbox + drafts del período de planilla)
    # ------------------------------------------------------------------ #
    def _stage_accounting(self, ctx: dict) -> dict:
        from apps.kernels.accounting.models import JournalDraft

        company = ctx["company"]
        drafts = JournalDraft.objects.filter(economic_event__company=company)
        by_state: dict[str, int] = {}
        for d in drafts:
            by_state[d.state] = by_state.get(d.state, 0) + 1
        return {"journal_drafts": drafts.count(), "by_state": by_state}
