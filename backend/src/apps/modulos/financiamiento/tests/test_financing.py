"""Tests del módulo financiamiento (reemplazo del SIFA-ACOPIO).

Cubre el ciclo completo del programa viejo: solicitud con garantías → aprobación
(SoD) → desembolso dual C$/US$ (doble saldo en portfolio) → abonos → acopio en
custodia → fijación de precio → liquidación con retenciones (abono COFFEE_QUOTA +
excedente CxP + traslado del café a inventario propio) → estado de cuenta. Más los
casos límite: SoD, depósito insuficiente, abono que excede saldo, monedas mezcladas,
cruce de moneda con tasa y devengo de interés del kernel sobre créditos del módulo.
"""
from __future__ import annotations

import uuid
from datetime import timedelta
from decimal import Decimal
from types import SimpleNamespace

import pytest
from django.contrib.auth import get_user_model
from django.utils import timezone

from apps.kernels.inventarios.models import InventoryItem, StockBalance, UoM
from apps.kernels.inventarios.services import create_warehouse
from apps.kernels.portfolio.models import Payable
from apps.kernels.portfolio.services import accrue_interest_for_credit
from apps.modulos.diagnostics.domain_map import risk_class_for_domain
from apps.modulos.financiamiento import services as fin
from apps.modulos.financiamiento.models import (
    ApplicationStatus,
    Currency,
    FixationStatus,
    LoanStatus,
)
from apps.modulos.financiamiento.services import FinancingError
from apps.modulos.iam.models import OrgUnit
from apps.modulos.org.module_catalog import get_spec
from apps.modulos.parties.models import Party, PartyRole

User = get_user_model()
UT = OrgUnit.UnitType


def _scope():
    t = uuid.uuid4().hex[:6]
    holding = OrgUnit.objects.create(unit_type=UT.HOLDING, name=f"H{t}", code=f"H-{t}")
    company = OrgUnit.objects.create(unit_type=UT.COMPANY, parent=holding, name=f"C{t}", code=f"C-{t}")
    branch = OrgUnit.objects.create(unit_type=UT.BRANCH, parent=company, name=f"B{t}", code=f"B-{t}")
    return holding, company, branch


def _user():
    t = uuid.uuid4().hex[:8]
    return User.objects.create_user(username=f"u_{t}", email=f"u_{t}@t.local", password="pass12345")


def _req(company, branch, user):
    return SimpleNamespace(
        company=company, branch=branch, user=user, META={}, headers={},
        path="/test/financiamiento/", method="POST", request_id=f"req-{uuid.uuid4().hex[:8]}",
    )


def _producer(company, name="Cooperativa La Esperanza", acopio="01-001"):
    party = Party.objects.create(
        company=company, party_type=Party.PartyType.NATURAL, display_name=name,
        national_id=f"001-{uuid.uuid4().hex[:9]}",
    )
    return fin.create_producer(company=company, party=party, acopio_code=acopio)


def _setup_acopio(req, company, branch, actor):
    """Bodegas custodia/propia + ítem café (libras) + calidad A configurados."""
    custody = create_warehouse(
        request=req, company=company, branch=branch, actor_user=actor,
        name="Custodia Café", code="CUST",
    )
    own = create_warehouse(
        request=req, company=company, branch=branch, actor_user=actor,
        name="Bodega Propia", code="PROP",
    )
    item = InventoryItem.objects.create(
        company=company, sku=f"CAFE-{uuid.uuid4().hex[:6]}", name="Café pergamino húmedo",
        uom=UoM.POUND,
    )
    row = fin.get_or_create_settings(company=company)
    row.coffee_item = item
    row.custody_warehouse = custody
    row.liquidation_warehouse = own
    row.save()
    quality = fin.create_quality_grade(
        company=company, code="A", name="Primera", default_tare_pct=Decimal("1.00"),
    )
    return custody, own, item, quality


def _dual_loan(req, company, *, oficial, comite, admin, nio="10000.00", usd="1000.00"):
    """Solicitud dual → submit → approve (comité) → disburse (admin). Devuelve (app, loan)."""
    producer = _producer(company)
    app = fin.create_application(
        company=company, producer=producer, actor=oficial,
        requested_nio=Decimal(nio), requested_usd=Decimal(usd), term_months=8,
        credit_type="AVIO", activity="Mantenimiento de café",
        interest_rate=Decimal("12.00"), penalty_rate=Decimal("4.00"),
        commission_rate=Decimal("2.00"),
        guarantee_farm_area_mz=Decimal("25.00"), guarantee_coffee_qq=Decimal("150.00"),
    )
    fin.submit_application(application=app)
    fin.approve_application(application=app, actor=comite, request=req)
    loan = fin.disburse_loan(request=_req(company, req.branch, admin), actor=admin, application=app)
    return app, loan


def _stock(company, branch, wh, item) -> Decimal:
    bal = StockBalance.objects.filter(company=company, branch=branch, warehouse=wh, item=item).first()
    return bal.qty_on_hand if bal else Decimal("0.0000")


# ===========================================================================
# E2E: el ciclo SIFA completo
# ===========================================================================

@pytest.mark.django_db
def test_ciclo_sifa_completo():
    _h, company, branch = _scope()
    oficial, comite, admin = _user(), _user(), _user()
    req = _req(company, branch, admin)
    custody, own, item, quality = _setup_acopio(req, company, branch, admin)
    fin.set_exchange_rate(company=company, rate_date=timezone.localdate(), rate=Decimal("36.50"))

    # --- F1: solicitud dual → aprobación → desembolso (doble saldo) ---
    app, loan = _dual_loan(req, company, oficial=oficial, comite=comite, admin=admin)
    app.refresh_from_db()
    assert app.status == ApplicationStatus.DISBURSED
    assert loan.credit_nio is not None and loan.credit_usd is not None
    # Comisión 2% como fee del kernel: outstanding = principal + fee.
    assert loan.credit_nio.outstanding_amount == Decimal("10200.00")
    assert loan.credit_usd.outstanding_amount == Decimal("1020.00")
    assert loan.credit_nio.late_payment_penalty_rate == Decimal("4.00")

    # --- Abono en efectivo al saldo córdobas ---
    pay = fin.register_loan_payment(
        request=req, actor=admin, loan=loan, amount=Decimal("2000.00"),
        paid_currency=Currency.NIO, payment_method="CASH",
    )
    assert pay["outstanding"] == "8200.00"

    # --- F2: acopio en custodia (tara por calidad y tara explícita) ---
    producer = loan.producer
    r1 = fin.receive_coffee(
        request=req, actor=admin, producer=producer, quality=quality,
        physical_state="HUMEDO", sacks=30, gross_lb=Decimal("3000.00"),
    )
    assert r1.tare_lb == Decimal("30.00")  # 1% por calidad A
    assert r1.net_lb == Decimal("2970.00")
    r2 = fin.receive_coffee(
        request=req, actor=admin, producer=producer, quality=quality,
        physical_state="MOJADO", sacks=20, gross_lb=Decimal("2030.00"), tare_lb=Decimal("30.00"),
    )
    assert r2.net_lb == Decimal("2000.00")
    assert _stock(company, branch, custody, item) == Decimal("4970.0000")

    deposit = fin.producer_deposit_balance(producer=producer)
    assert deposit["available_lb"] == "4970.00"

    # --- Fijación de precio (compromete las libras) ---
    fx = fin.fix_price(
        company=company, producer=producer, pounds=Decimal("3000.00"),
        price_per_lb=Decimal("0.80"), currency=Currency.USD,
    )
    assert fin.producer_deposit_balance(producer=producer)["available_lb"] == "1970.00"

    # --- Liquidación: retención + abono al saldo US$ + excedente CxP + traslado ---
    liq = fin.liquidate(
        request=req, actor=admin, producer=producer, fixation_ids=[fx.pk], loan=loan,
        deductions=[{"concept": "Aporte cooperativa", "amount": Decimal("100.00")}],
    )
    assert liq.gross_value == Decimal("2400.00")          # 3000 lb × 0.80
    assert liq.deductions_total == Decimal("100.00")
    assert liq.applied_to_loan == Decimal("1020.00")      # saldo US$ completo
    assert liq.applied_currency == Currency.USD
    assert liq.surplus_amount == Decimal("1280.00")       # 2300 − 1020
    assert liq.payable is not None
    assert Payable.objects.get(pk=liq.payable_id).principal_amount == Decimal("1280.00")
    fx.refresh_from_db()
    assert fx.status == FixationStatus.LIQUIDATED

    loan.credit_usd.refresh_from_db()
    assert loan.credit_usd.outstanding_amount == Decimal("0.00")

    # Café: salió de custodia y entró a bodega propia con costo de compra.
    assert _stock(company, branch, custody, item) == Decimal("1970.0000")
    assert _stock(company, branch, own, item) == Decimal("3000.0000")
    own_bal = StockBalance.objects.get(company=company, branch=branch, warehouse=own, item=item)
    assert own_bal.avg_cost == Decimal("29.2000")  # 2400 × 36.50 / 3000 lb

    # --- Estado de cuenta consolidado ---
    st = fin.loan_statement(loan=loan)
    assert st["balances"]["USD"]["outstanding"] == "0.00"
    assert st["balances"]["NIO"]["outstanding"] == "8200.00"
    assert st["consolidated_nio"] == "8200.00"
    assert loan.status == LoanStatus.ACTIVE

    # --- Cancela el saldo córdobas → préstamo PAGADO ---
    fin.register_loan_payment(
        request=req, actor=admin, loan=loan, amount=Decimal("8200.00"),
        paid_currency=Currency.NIO, payment_method="TRANSFER",
    )
    loan.refresh_from_db()
    assert loan.status == LoanStatus.PAID


# ===========================================================================
# SoD: quien registra no aprueba; quien aprueba no desembolsa
# ===========================================================================

@pytest.mark.django_db
def test_sod_creador_no_aprueba_y_aprobador_no_desembolsa():
    _h, company, branch = _scope()
    oficial, comite = _user(), _user()
    req = _req(company, branch, comite)
    producer = _producer(company)
    app = fin.create_application(
        company=company, producer=producer, actor=oficial,
        requested_nio=Decimal("5000.00"), term_months=6, interest_rate=Decimal("10.00"),
    )
    fin.submit_application(application=app)
    with pytest.raises(FinancingError) as exc:
        fin.approve_application(application=app, actor=oficial)
    assert exc.value.code == "FIN_SOD_VIOLATION"

    fin.approve_application(application=app, actor=comite)
    with pytest.raises(FinancingError) as exc:
        fin.disburse_loan(request=req, actor=comite, application=app)
    assert exc.value.code == "FIN_SOD_VIOLATION"


# ===========================================================================
# Validaciones de negocio
# ===========================================================================

@pytest.mark.django_db
def test_solicitud_sin_montos_falla():
    _h, company, _branch = _scope()
    producer = _producer(company)
    with pytest.raises(FinancingError) as exc:
        fin.create_application(
            company=company, producer=producer, term_months=6, interest_rate=Decimal("10.00"),
        )
    assert exc.value.code == "FIN_AMOUNT_INVALID"


@pytest.mark.django_db
def test_fijacion_excede_deposito():
    _h, company, branch = _scope()
    admin = _user()
    req = _req(company, branch, admin)
    _custody, _own, _item, quality = _setup_acopio(req, company, branch, admin)
    producer = _producer(company)
    fin.receive_coffee(
        request=req, actor=admin, producer=producer, quality=quality,
        physical_state="HUMEDO", sacks=10, gross_lb=Decimal("1000.00"), tare_lb=Decimal("0.00"),
    )
    with pytest.raises(FinancingError) as exc:
        fin.fix_price(
            company=company, producer=producer, pounds=Decimal("1500.00"),
            price_per_lb=Decimal("0.80"),
        )
    assert exc.value.code == "FIN_DEPOSIT_INSUFFICIENT"


@pytest.mark.django_db
def test_abono_excede_saldo():
    _h, company, branch = _scope()
    oficial, comite, admin = _user(), _user(), _user()
    req = _req(company, branch, admin)
    _setup_acopio(req, company, branch, admin)
    _app, loan = _dual_loan(req, company, oficial=oficial, comite=comite, admin=admin, usd="0.00")
    with pytest.raises(FinancingError) as exc:
        fin.register_loan_payment(
            request=req, actor=admin, loan=loan, amount=Decimal("99999.00"),
            paid_currency=Currency.NIO,
        )
    assert exc.value.code == "FIN_PAYMENT_EXCEEDS_OUTSTANDING"


@pytest.mark.django_db
def test_abono_cruzado_usd_a_saldo_nio_con_tasa():
    """Paga US$ sobre el saldo en córdobas: convierte con la tasa del día."""
    _h, company, branch = _scope()
    oficial, comite, admin = _user(), _user(), _user()
    req = _req(company, branch, admin)
    _setup_acopio(req, company, branch, admin)
    fin.set_exchange_rate(company=company, rate_date=timezone.localdate(), rate=Decimal("36.00"))
    _app, loan = _dual_loan(req, company, oficial=oficial, comite=comite, admin=admin, usd="0.00")
    # Saldo NIO = 10,000 + 200 comisión. Paga 100 US$ → abona 3,600 C$.
    out = fin.register_loan_payment(
        request=req, actor=admin, loan=loan, amount=Decimal("100.00"),
        paid_currency=Currency.USD, target_currency=Currency.NIO,
    )
    assert out["allocated"] == "3600.00"
    assert out["outstanding"] == "6600.00"


@pytest.mark.django_db
def test_liquidacion_no_mezcla_monedas_y_no_reliquida():
    _h, company, branch = _scope()
    admin = _user()
    req = _req(company, branch, admin)
    _setup_acopio(req, company, branch, admin)
    fin.set_exchange_rate(company=company, rate_date=timezone.localdate(), rate=Decimal("36.50"))
    producer = _producer(company)
    quality = fin.create_quality_grade(company=company, code="B", name="Segunda")
    fin.receive_coffee(
        request=req, actor=admin, producer=producer, quality=quality,
        physical_state="SECO", sacks=50, gross_lb=Decimal("5000.00"), tare_lb=Decimal("0.00"),
    )
    f_usd = fin.fix_price(company=company, producer=producer, pounds=Decimal("1000.00"),
                          price_per_lb=Decimal("0.80"), currency=Currency.USD)
    f_nio = fin.fix_price(company=company, producer=producer, pounds=Decimal("1000.00"),
                          price_per_lb=Decimal("30.00"), currency=Currency.NIO)
    with pytest.raises(FinancingError) as exc:
        fin.liquidate(request=req, actor=admin, producer=producer,
                      fixation_ids=[f_usd.pk, f_nio.pk])
    assert exc.value.code == "FIN_FIXATION_MIXED"

    liq = fin.liquidate(request=req, actor=admin, producer=producer, fixation_ids=[f_usd.pk])
    assert liq.surplus_amount == Decimal("800.00")  # sin préstamo: todo excedente
    with pytest.raises(FinancingError) as exc:
        fin.liquidate(request=req, actor=admin, producer=producer, fixation_ids=[f_usd.pk])
    assert exc.value.code == "FIN_FIXATION_STATE"


@pytest.mark.django_db
def test_recepcion_sin_configuracion_falla():
    _h, company, branch = _scope()
    admin = _user()
    req = _req(company, branch, admin)
    producer = _producer(company)
    quality = fin.create_quality_grade(company=company, code="A", name="Primera")
    with pytest.raises(FinancingError) as exc:
        fin.receive_coffee(
            request=req, actor=admin, producer=producer, quality=quality,
            physical_state="HUMEDO", sacks=1, gross_lb=Decimal("100.00"),
        )
    assert exc.value.code == "FIN_SETTINGS_INCOMPLETE"


# ===========================================================================
# Integración con los kernels y la plataforma
# ===========================================================================

@pytest.mark.django_db
def test_devengo_de_interes_del_kernel_sobre_credito_del_modulo():
    _h, company, branch = _scope()
    oficial, comite, admin = _user(), _user(), _user()
    req = _req(company, branch, admin)
    _setup_acopio(req, company, branch, admin)
    _app, loan = _dual_loan(req, company, oficial=oficial, comite=comite, admin=admin, usd="0.00")
    credit = loan.credit_nio
    before = credit.outstanding_amount
    today = timezone.localdate()
    accrual = accrue_interest_for_credit(credit, today, today - timedelta(days=30), today)
    assert accrual is not None and accrual.accrued_interest > 0
    credit.refresh_from_db()
    assert credit.outstanding_amount > before


@pytest.mark.django_db
def test_productor_recibe_rol_de_party():
    _h, company, _branch = _scope()
    producer = _producer(company)
    assert PartyRole.objects.filter(
        party=producer.party, role=PartyRole.Role.PRODUCER, is_active=True
    ).exists()


def test_modulo_registrado_en_catalogo_y_clasificado_c1():
    spec = get_spec("financiamiento")
    assert spec is not None
    assert spec.category == "VERTICAL"
    assert spec.default_enabled is False  # opt-in por empresa (CompanyModule)
    assert "financing." in spec.permission_prefixes
    # Dinero + stock ⇒ dominio crítico para diagnostics.
    assert risk_class_for_domain("financiamiento") == "C1"
