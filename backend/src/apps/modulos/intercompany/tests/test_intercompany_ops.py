"""Tests del seam de consolidación intercompany (operación A→B + eliminación).

Prueba que una operación entre dos empresas del grupo dispara todas sus patas
(GL en cada empresa + CxC en A + CxP en B + enlace IntercompanyTransaction) y que
`run_consolidation` consolida sin doble conteo. Espeja el patrón probado de
`tests/test_phase7b_intercompany_consolidation.py`.
"""
from __future__ import annotations

import uuid
from datetime import date
from decimal import Decimal

import pytest
from django.contrib.auth import get_user_model
from rest_framework.test import APIClient

from apps.kernels.accounting.models import ChartOfAccount, ConsolidationRun, IntercompanyTransaction
from apps.kernels.accounting.phase7b import run_consolidation
from apps.kernels.portfolio.models import Payable, Receivable
from apps.modulos.iam.models import CompanyLink, LinkGrant, OrgUnit, UserMembership
from apps.modulos.intercompany.services import group_cartera_position, record_intercompany_charge
from apps.modulos.parties.models import Party
from apps.modulos.rbac.models import Permission, Role, RoleAssignment, RolePermission

User = get_user_model()
UT = OrgUnit.UnitType
IC_WRITE = "accounting.intercompany.write"


def _mk_orgs():
    s = uuid.uuid4().hex[:5]
    holding = OrgUnit.objects.create(unit_type=UT.HOLDING, name=f"Holding {s}")
    a = OrgUnit.objects.create(unit_type=UT.COMPANY, name=f"Comisariato {s}", parent=holding)
    a_br = OrgUnit.objects.create(unit_type=UT.BRANCH, name=f"Oficina {s}", parent=a)
    b = OrgUnit.objects.create(unit_type=UT.COMPANY, name=f"Cafetalera {s}", parent=holding)
    b_br = OrgUnit.objects.create(unit_type=UT.BRANCH, name=f"Finca {s}", parent=b)
    return holding, a, a_br, b, b_br


def _seed_coa(company: OrgUnit):
    rows = {
        "1301": ("CxC Intercompany", ChartOfAccount.AccountType.ASSET),
        "2109": ("CxP Intercompany", ChartOfAccount.AccountType.LIABILITY),
        "4101": ("Ingresos Intercompany", ChartOfAccount.AccountType.REVENUE),
        "5101": ("Gasto Intercompany", ChartOfAccount.AccountType.EXPENSE),
    }
    for code, (name, atype) in rows.items():
        ChartOfAccount.objects.create(
            company=company, code=code, name=name, account_type=atype, is_postable=True, is_active=True
        )


def _grant(*, from_company: OrgUnit, to_company: OrgUnit, permission_code: str = IC_WRITE):
    perm, _ = Permission.objects.get_or_create(
        code=permission_code, defaults={"description": permission_code, "is_active": True}
    )
    link, _ = CompanyLink.objects.get_or_create(
        from_company=from_company, to_company=to_company,
        defaults={"status": CompanyLink.Status.ACTIVE, "is_active": True},
    )
    LinkGrant.objects.update_or_create(
        link=link, permission=perm, access_mode=LinkGrant.AccessMode.WRITE, scope_org_unit=None,
        defaults={"is_active": True, "valid_from": None, "valid_to": None},
    )


def _mk_user(prefix="u"):
    u = f"{prefix}_{uuid.uuid4().hex[:8]}"
    return User.objects.create_user(username=u, email=f"{u}@t.local", password="pass12345")


def _setup(*, granted=True):
    holding, a, a_br, b, b_br = _mk_orgs()
    _seed_coa(a)
    _seed_coa(b)
    if granted:
        # create+confirm actúan desde source(A): grant from_company=target(B) -> to_company=source(A)
        _grant(from_company=b, to_company=a)
    return holding, a, a_br, b, b_br, _mk_user("ic")


# ---------------------------------------------------------------------------
# Servicio
# ---------------------------------------------------------------------------

@pytest.mark.django_db
def test_record_intercompany_charge_full_loop():
    holding, a, a_br, b, b_br, user = _setup()
    res = record_intercompany_charge(
        source_company_id=a.id, target_company_id=b.id, amount="1000.00",
        reference_code="IC-001", concept="Suministro insumos", effective_date=date(2026, 3, 15), actor=user,
    )
    assert res["status"] == IntercompanyTransaction.Status.CONFIRMED
    assert res["source_journal_entry_id"] and res["target_journal_entry_id"]

    rec = Receivable.objects.get(id=res["receivable_id"])
    assert rec.company_id == a.id and rec.principal_amount == Decimal("1000.00")
    assert rec.party.party_type == Party.PartyType.INTERNAL and rec.party.display_name == b.name
    pay = Payable.objects.get(id=res["payable_id"])
    assert pay.company_id == b.id and pay.principal_amount == Decimal("1000.00")
    assert pay.party.display_name == a.name


@pytest.mark.django_db
def test_consolidation_consumes_charge_and_balances():
    holding, a, a_br, b, b_br, user = _setup()
    record_intercompany_charge(
        source_company_id=a.id, target_company_id=b.id, amount="1000.00",
        reference_code="IC-002", effective_date=date(2026, 3, 10), actor=user,
    )
    result = run_consolidation(
        parent_company_id=a.id, year=2026, month=3, company_ids=[a.id, b.id], strict=True, actor_user=user,
    )
    assert result.status == ConsolidationRun.Status.COMPLETED
    # Ingreso IC (A) y Gasto IC (B) se compensan en el grupo: utilidad neta consolidada = 0.
    assert result.summary_json["pnl"]["totals"]["net_income"] == "0.00"


@pytest.mark.django_db
def test_idempotent_by_reference_code():
    holding, a, a_br, b, b_br, user = _setup()
    kwargs = dict(source_company_id=a.id, target_company_id=b.id, amount="500.00",
                  reference_code="IC-DUP", effective_date=date(2026, 3, 1), actor=user)
    r1 = record_intercompany_charge(**kwargs)
    r2 = record_intercompany_charge(**kwargs)
    assert r1["tx_id"] == r2["tx_id"]
    assert IntercompanyTransaction.objects.filter(reference_code="IC-DUP").count() == 1
    assert Receivable.objects.filter(company=a).count() == 1
    assert Payable.objects.filter(company=b).count() == 1


@pytest.mark.django_db
def test_not_authorized_without_grant():
    holding, a, a_br, b, b_br, user = _setup(granted=False)
    with pytest.raises(ValueError, match="INTERCOMPANY_NOT_AUTHORIZED"):
        record_intercompany_charge(
            source_company_id=a.id, target_company_id=b.id, amount="100.00",
            reference_code="IC-NO", effective_date=date(2026, 3, 1), actor=user,
        )
    # Sin estado parcial (rollback): no se posteó nada.
    assert IntercompanyTransaction.objects.count() == 0
    assert Receivable.objects.count() == 0


@pytest.mark.django_db
def test_group_cartera_position_separates_intercompany():
    holding, a, a_br, b, b_br, user = _setup()
    record_intercompany_charge(
        source_company_id=a.id, target_company_id=b.id, amount="700.00",
        reference_code="IC-POS", effective_date=date(2026, 3, 1), actor=user,
    )
    pos = group_cartera_position(company_ids=[a.id, b.id])
    by = {row["company_id"]: row for row in pos["by_company"]}
    assert by[a.id]["cxc_intercompany"] == "700.00"
    assert by[b.id]["cxp_intercompany"] == "700.00"


# ---------------------------------------------------------------------------
# HTTP + RBAC
# ---------------------------------------------------------------------------

def _client(user, company, branch, perms: list[str]) -> APIClient:
    UserMembership.objects.get_or_create(user=user, org_unit=company, defaults={"is_active": True})
    UserMembership.objects.get_or_create(user=user, org_unit=branch, defaults={"is_active": True})
    role = Role.objects.create(name=f"r_{uuid.uuid4().hex[:8]}", is_active=True)
    for code in perms:
        perm, _ = Permission.objects.get_or_create(code=code, defaults={"description": code, "is_active": True})
        RolePermission.objects.get_or_create(role=role, permission=perm)
    RoleAssignment.objects.create(user=user, role=role, org_unit=company, is_active=True)
    RoleAssignment.objects.create(user=user, role=role, org_unit=branch, is_active=True)
    c = APIClient()
    login = c.post("/api/auth/login/", {"username": user.username, "password": "pass12345"},
                   format="json", HTTP_X_AUTH_TRANSPORT="header")
    assert login.status_code == 200, login.data
    c.credentials(HTTP_AUTHORIZATION=f"Bearer {login.data.get('access')}")
    c.defaults["HTTP_X_AUTH_TRANSPORT"] = "header"
    c.defaults["HTTP_X_COMPANY_ID"] = str(company.id)
    c.defaults["HTTP_X_BRANCH_ID"] = str(branch.id)
    return c


@pytest.mark.django_db
def test_charge_endpoint_forbidden_without_perm():
    holding, a, a_br, b, b_br, user = _setup()
    api = _client(_mk_user("n"), a, a_br, ["audit.read"])  # sin accounting.intercompany.write
    r = api.post("/api/intercompany/charges/",
                 {"source_company_id": a.id, "target_company_id": b.id, "amount": "100.00", "reference_code": "IC-F"},
                 format="json")
    assert r.status_code == 403


@pytest.mark.django_db
def test_charge_endpoint_and_group_cartera_http():
    holding, a, a_br, b, b_br, user = _setup()
    api = _client(_mk_user("adm"), a, a_br, [IC_WRITE, "audit.read"])

    r = api.post("/api/intercompany/charges/",
                 {"source_company_id": a.id, "target_company_id": b.id, "amount": "900.00",
                  "reference_code": "IC-HTTP", "effective_date": "2026-03-05", "concept": "Flete"},
                 format="json")
    assert r.status_code == 201, r.data
    assert r.data["status"] == "CONFIRMED"

    r = api.get(f"/api/intercompany/group-cartera/?company_ids={a.id},{b.id}")
    assert r.status_code == 200, r.data
    by = {row["company_id"]: row for row in r.data["by_company"]}
    assert by[a.id]["cxc_intercompany"] == "900.00"
