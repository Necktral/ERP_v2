"""Servicios del módulo FINANCIAMIENTO: orquestación pura sobre los kernels.

Flujo SIFA completo: solicitud (garantías) → aprobación (SoD) → desembolso (1-2
``portfolio.Credit``, doble saldo C$/US$) → abonos (PaymentIntent + allocation) →
acopio en custodia (``inventarios.post_receive`` costo 0) → fijación de precio →
liquidación (valor − retenciones → abono COFFEE_QUOTA al crédito → excedente CxP →
café pasa de custodia a inventario propio con costo de compra).

Ninguna regla de dinero/stock se reimplementa aquí: el outstanding, el devengo de
interés, la mora y el kardex son del kernel. Este módulo solo encadena.
"""
from __future__ import annotations

import uuid
from datetime import date
from decimal import Decimal, ROUND_HALF_UP
from typing import Any, Optional

from django.db import transaction
from django.utils import timezone

from apps.kernels.inventarios.services import post_issue, post_receive
from apps.kernels.payments.services import (
    capture_payment_intent_for_scope,
    create_payment_intent_for_scope,
)
from apps.kernels.portfolio.models import Credit
from apps.kernels.portfolio.services import (
    allocate_payment_to_obligation,
    create_credit,
    create_payable,
    disburse_credit,
)
from apps.modulos.audit.writer import write_event
from apps.modulos.common.tender import TenderPaymentMethod
from apps.modulos.iam.models import OrgUnit
from apps.modulos.integration.services import publish_outbox_event
from apps.modulos.parties.models import Party, PartyRole

from .models import (
    ApplicationStatus,
    CoffeeQualityGrade,
    CoffeeReception,
    CreditApplication,
    Currency,
    ExchangeRate,
    FinancingLoan,
    FinancingSettings,
    FixationStatus,
    Liquidation,
    LiquidationDeduction,
    LoanStatus,
    PriceFixation,
    ProducerProfile,
)

_TWO = Decimal("0.01")


class FinancingError(Exception):
    """Error de negocio del vertical (code estable + mensaje legible)."""

    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code
        self.message = message


def _q2(x: Decimal) -> Decimal:
    return x.quantize(_TWO, rounding=ROUND_HALF_UP)


def _add_months(d: date, months: int) -> date:
    month = d.month - 1 + months
    year = d.year + month // 12
    month = month % 12 + 1
    # Día válido del mes destino (28-31).
    day = min(d.day, [31, 29 if year % 4 == 0 and (year % 100 != 0 or year % 400 == 0) else 28,
                      31, 30, 31, 30, 31, 31, 30, 31, 30, 31][month - 1])
    return date(year, month, day)


# ---------------------------------------------------------------------------
# Configuración y catálogos
# ---------------------------------------------------------------------------

def get_or_create_settings(*, company: OrgUnit) -> FinancingSettings:
    """Config del vertical; crea el party INTERNAL acreedor si no existe."""
    existing = FinancingSettings.objects.filter(company=company).first()
    if existing:
        return existing
    lender = Party.objects.filter(
        company=company, party_type=Party.PartyType.INTERNAL, display_name=company.name
    ).first()
    if lender is None:
        lender = Party.objects.create(
            company=company, party_type=Party.PartyType.INTERNAL, display_name=company.name,
        )
    return FinancingSettings.objects.create(company=company, lender_party=lender)


def set_exchange_rate(*, company: OrgUnit, rate_date: date, rate: Decimal, actor=None) -> ExchangeRate:
    if rate <= 0:
        raise FinancingError("FIN_RATE_INVALID", "La tasa de cambio debe ser positiva.")
    obj, _created = ExchangeRate.objects.update_or_create(
        company=company, rate_date=rate_date,
        defaults={"rate": rate, "created_by": actor if getattr(actor, "pk", None) else None},
    )
    return obj


def rate_for(*, company: OrgUnit, as_of: date) -> Optional[Decimal]:
    """Tasa vigente: la más reciente con fecha ≤ ``as_of``."""
    row = (
        ExchangeRate.objects.filter(company=company, rate_date__lte=as_of)
        .order_by("-rate_date")
        .first()
    )
    return row.rate if row else None


def create_producer(
    *, company: OrgUnit, party: Party, acopio_code: str = "", certifications: str = "",
    notes: str = "", actor=None,
) -> ProducerProfile:
    if party.company_id != company.id:
        raise FinancingError("FIN_PARTY_SCOPE", "El party pertenece a otra empresa.")
    existing = ProducerProfile.objects.filter(company=company, party=party).first()
    if existing:
        return existing
    # El productor queda con su rol de party (ortogonal al perfil del vertical).
    PartyRole.objects.get_or_create(
        party=party, role=PartyRole.Role.PRODUCER, defaults={"is_active": True},
    )
    return ProducerProfile.objects.create(
        company=company, party=party, acopio_code=acopio_code,
        certifications=certifications, notes=notes,
    )


def create_quality_grade(
    *, company: OrgUnit, code: str, name: str, default_tare_pct: Decimal = Decimal("0.00"),
) -> CoffeeQualityGrade:
    obj, _created = CoffeeQualityGrade.objects.get_or_create(
        company=company, code=code, defaults={"name": name, "default_tare_pct": default_tare_pct},
    )
    return obj


# ---------------------------------------------------------------------------
# F1 — Solicitud → aprobación (SoD) → desembolso → abonos → estado de cuenta
# ---------------------------------------------------------------------------

def create_application(*, company: OrgUnit, producer: ProducerProfile, actor=None, **fields) -> CreditApplication:
    requested_nio = Decimal(fields.get("requested_nio") or "0")
    requested_usd = Decimal(fields.get("requested_usd") or "0")
    if requested_nio < 0 or requested_usd < 0:
        raise FinancingError("FIN_AMOUNT_INVALID", "Los montos solicitados no pueden ser negativos.")
    if requested_nio == 0 and requested_usd == 0:
        raise FinancingError("FIN_AMOUNT_INVALID", "Debe solicitar monto en córdobas, dólares o ambos.")
    if producer.company_id != company.id:
        raise FinancingError("FIN_PRODUCER_SCOPE", "El productor pertenece a otra empresa.")
    return CreditApplication.objects.create(
        company=company,
        producer=producer,
        requested_nio=_q2(requested_nio),
        requested_usd=_q2(requested_usd),
        term_months=int(fields.get("term_months") or 0) or 1,
        credit_type=fields.get("credit_type", ""),
        activity=fields.get("activity", ""),
        interest_rate=Decimal(fields.get("interest_rate") or "0"),
        penalty_rate=Decimal(fields.get("penalty_rate") or "0"),
        commission_rate=Decimal(fields.get("commission_rate") or "0"),
        disbursement_form=fields.get("disbursement_form") or "CASH",
        guarantee_farm_area_mz=Decimal(fields.get("guarantee_farm_area_mz") or "0"),
        guarantee_solar=fields.get("guarantee_solar", ""),
        guarantee_other=fields.get("guarantee_other", ""),
        guarantee_coffee_qq=Decimal(fields.get("guarantee_coffee_qq") or "0"),
        created_by=actor if getattr(actor, "pk", None) else None,
    )


def submit_application(*, application: CreditApplication) -> CreditApplication:
    if application.status != ApplicationStatus.DRAFT:
        raise FinancingError("FIN_APP_STATE", f"Solo un borrador se puede presentar (está {application.status}).")
    application.status = ApplicationStatus.SUBMITTED
    application.submitted_at = timezone.now()
    application.save(update_fields=["status", "submitted_at", "updated_at"])
    return application


def approve_application(*, application: CreditApplication, actor, request=None) -> CreditApplication:
    """Aprueba la solicitud. SoD: quien la creó no puede aprobarla."""
    if application.status != ApplicationStatus.SUBMITTED:
        raise FinancingError("FIN_APP_STATE", f"Solo una solicitud presentada se aprueba (está {application.status}).")
    actor_pk = getattr(actor, "pk", None)
    if actor_pk and application.created_by_id and actor_pk == application.created_by_id:
        raise FinancingError("FIN_SOD_VIOLATION", "Quien registró la solicitud no puede aprobarla (SoD).")
    application.status = ApplicationStatus.APPROVED
    application.decided_at = timezone.now()
    application.decided_by = actor if actor_pk else None
    application.save(update_fields=["status", "decided_at", "decided_by", "updated_at"])
    if request is not None:
        write_event(
            request=request, event_type="FINANCING_APPLICATION_APPROVED",
            actor_user=actor, subject_type="FINANCING_APPLICATION", subject_id=str(application.pk),
            module="financiamiento",
        )
    return application


def reject_application(*, application: CreditApplication, actor, reason: str = "") -> CreditApplication:
    if application.status != ApplicationStatus.SUBMITTED:
        raise FinancingError("FIN_APP_STATE", f"Solo una solicitud presentada se rechaza (está {application.status}).")
    application.status = ApplicationStatus.REJECTED
    application.decided_at = timezone.now()
    application.decided_by = actor if getattr(actor, "pk", None) else None
    application.rejection_reason = reason[:500]
    application.save(update_fields=["status", "decided_at", "decided_by", "rejection_reason", "updated_at"])
    return application


def _next_loan_reference(company: OrgUnit) -> str:
    seq = FinancingLoan.objects.filter(company=company).count() + 1
    return f"PTMO-{company.pk}-{seq:05d}"


def _create_currency_credit(
    *, company, settings_row, producer, amount: Decimal, currency: str, application,
    disbursement_date: date, maturity: date, actor,
) -> Credit:
    credit = create_credit(
        company=company,
        credit_type="WORKING_CAPITAL",
        lender_party=settings_row.lender_party,
        borrower_party=producer.party,
        approved_amount=amount,
        currency=currency,
        interest_rate=application.interest_rate,
        term_months=application.term_months,
        maturity_date=maturity,
        collateral_type="COFFEE" if application.guarantee_coffee_qq > 0 else "",
        collateral_value=application.guarantee_coffee_qq or None,
        created_by=actor if getattr(actor, "pk", None) else None,
        metadata={"financing_application_id": application.pk, "sifa_dual_currency": True},
    )
    # Comisión y mora del SIFA: viven en los campos del kernel (fee/penalty).
    commission = _q2(amount * application.commission_rate / Decimal("100"))
    updates = []
    if commission > 0:
        credit.fee_amount = commission
        updates.append("fee_amount")
    if application.penalty_rate > 0:
        credit.late_payment_penalty_rate = application.penalty_rate
        updates.append("late_payment_penalty_rate")
    if updates:
        credit.save(update_fields=updates)
    disburse_credit(credit, amount, disbursement_date, actor)
    return credit


@transaction.atomic
def disburse_loan(
    *, request, actor, application: CreditApplication,
    disbursement_date: Optional[date] = None, reference: str = "",
) -> FinancingLoan:
    """Crea el préstamo dual-moneda: un ``portfolio.Credit`` por moneda con monto > 0."""
    company: OrgUnit = request.company
    if application.company_id != company.id:
        raise FinancingError("FIN_APP_SCOPE", "La solicitud pertenece a otra empresa.")
    if application.status != ApplicationStatus.APPROVED:
        raise FinancingError("FIN_APP_STATE", f"Solo una solicitud aprobada se desembolsa (está {application.status}).")
    # SoD: quien aprobó no desembolsa.
    actor_pk = getattr(actor, "pk", None)
    if actor_pk and application.decided_by_id and actor_pk == application.decided_by_id:
        raise FinancingError("FIN_SOD_VIOLATION", "Quien aprobó la solicitud no puede desembolsarla (SoD).")

    settings_row = get_or_create_settings(company=company)
    when = disbursement_date or timezone.localdate()
    maturity = _add_months(when, application.term_months)
    producer = application.producer

    loan = FinancingLoan.objects.create(
        company=company,
        producer=producer,
        application=application,
        reference=reference or _next_loan_reference(company),
        credit_type=application.credit_type,
        activity=application.activity,
        interest_rate=application.interest_rate,
        penalty_rate=application.penalty_rate,
        commission_rate=application.commission_rate,
        term_months=application.term_months,
        maturity_date=maturity,
        disbursement_form=application.disbursement_form,
        disbursed_at=when,
        created_by=actor if actor_pk else None,
    )
    if application.requested_nio > 0:
        loan.credit_nio = _create_currency_credit(
            company=company, settings_row=settings_row, producer=producer,
            amount=application.requested_nio, currency=Currency.NIO, application=application,
            disbursement_date=when, maturity=maturity, actor=actor,
        )
    if application.requested_usd > 0:
        loan.credit_usd = _create_currency_credit(
            company=company, settings_row=settings_row, producer=producer,
            amount=application.requested_usd, currency=Currency.USD, application=application,
            disbursement_date=when, maturity=maturity, actor=actor,
        )
    loan.save(update_fields=["credit_nio", "credit_usd", "updated_at"])

    application.status = ApplicationStatus.DISBURSED
    application.save(update_fields=["status", "updated_at"])

    publish_outbox_event(
        request=request, source_module="FINANCING", event_type="LoanDisbursed",
        payload={
            "loan_id": loan.pk, "reference": loan.reference, "producer_id": producer.pk,
            "amount_nio": str(application.requested_nio), "amount_usd": str(application.requested_usd),
            "maturity_date": maturity.isoformat(),
        },
        actor_user=actor, company=company, branch=getattr(request, "branch", None),
    )
    write_event(
        request=request, event_type="FINANCING_LOAN_DISBURSED",
        actor_user=actor, subject_type="FINANCING_LOAN", subject_id=str(loan.pk),
        module="financiamiento",
        metadata={"nio": str(application.requested_nio), "usd": str(application.requested_usd)},
    )
    return loan


def _refresh_loan_status(loan: FinancingLoan) -> None:
    credits = [c for c in (loan.credit_nio, loan.credit_usd) if c is not None]
    if credits and all(c.outstanding_amount <= 0 for c in credits):
        loan.status = LoanStatus.PAID
        loan.save(update_fields=["status", "updated_at"])


@transaction.atomic
def register_loan_payment(
    *, request, actor, loan: FinancingLoan, amount: Decimal, paid_currency: str,
    target_currency: str = "", payment_method: str = "CASH",
    exchange_rate: Optional[Decimal] = None, payment_date: Optional[date] = None,
    idempotency_key: str = "",
) -> dict[str, Any]:
    """Abono al préstamo (ReciboDeCaja del SIFA). Si la moneda pagada difiere del
    saldo destino, convierte con la tasa (param o vigente del día)."""
    company: OrgUnit = request.company
    if loan.company_id != company.id:
        raise FinancingError("FIN_LOAN_SCOPE", "El préstamo pertenece a otra empresa.")
    amount = _q2(Decimal(amount))
    if amount <= 0:
        raise FinancingError("FIN_AMOUNT_INVALID", "El abono debe ser positivo.")
    when = payment_date or timezone.localdate()

    target = target_currency or paid_currency
    credit = loan.credit_for(target)
    if credit is None:
        raise FinancingError("FIN_NO_BALANCE", f"El préstamo no tiene saldo en {target}.")

    rate = exchange_rate
    if paid_currency != target:
        rate = rate or rate_for(company=company, as_of=when)
        if not rate:
            raise FinancingError("FIN_RATE_REQUIRED", "No hay tasa de cambio vigente para convertir el abono.")
        if paid_currency == Currency.NIO:  # paga C$ sobre saldo US$
            allocated = _q2(amount / rate)
        else:  # paga US$ sobre saldo C$
            allocated = _q2(amount * rate)
    else:
        allocated = amount

    outstanding = credit.outstanding_amount
    if allocated > outstanding:
        raise FinancingError(
            "FIN_PAYMENT_EXCEEDS_OUTSTANDING",
            f"El abono ({allocated} {target}) excede el saldo ({outstanding} {target}).",
        )

    # El intent vive en la moneda de la obligación (igual que la liquidación): el kernel
    # compara allocated vs amount en el mismo número, así que el cruce se convierte ANTES.
    # El tender físico original queda en external_ref y la tasa en la allocation.
    cross_note = (
        f"pagado {amount} {paid_currency} @ {rate}" if paid_currency != target else ""
    )
    intent, _idem = create_payment_intent_for_scope(
        company=company, branch=request.branch, actor=actor, request=request,
        amount=allocated, currency=target,
        idempotency_key=idempotency_key or f"fin-pay-{uuid.uuid4().hex}",
        payment_method=payment_method,
        external_ref=cross_note,
    )
    intent = capture_payment_intent_for_scope(
        company=company, branch=request.branch, actor=actor,
        payment_id=intent.payment_id, request=request,
    )
    allocation = allocate_payment_to_obligation(
        intent, credit, allocated, when, actor,
        exchange_rate=rate if paid_currency != target else None,
    )
    credit.refresh_from_db()
    _refresh_loan_status(loan)
    return {
        "payment_id": str(intent.payment_id),
        "allocation_id": allocation.pk,
        "allocated": str(allocated),
        "target_currency": target,
        "outstanding": str(credit.outstanding_amount),
        "loan_status": loan.status,
    }


def loan_statement(*, loan: FinancingLoan, as_of: Optional[date] = None) -> dict[str, Any]:
    """Estado de cuenta (pantalla `ESTADO DE CUENTAS` del SIFA): por moneda y
    consolidado en córdobas con la tasa vigente."""
    when = as_of or timezone.localdate()
    out: dict[str, Any] = {
        "loan_id": loan.pk, "reference": loan.reference, "status": loan.status,
        "producer": loan.producer.party.display_name,
        "maturity_date": loan.maturity_date.isoformat(),
        "balances": {}, "consolidated_nio": None, "rate_used": None,
    }
    for ccy, credit in ((Currency.NIO, loan.credit_nio), (Currency.USD, loan.credit_usd)):
        if credit is None:
            continue
        out["balances"][str(ccy)] = {
            "principal": str(credit.principal_amount),
            "interest": str(credit.interest_amount),
            "fee": str(credit.fee_amount),
            "penalty": str(credit.penalty_amount),
            "allocated": str(credit.allocated_amount),
            "outstanding": str(credit.outstanding_amount),
            "days_overdue": credit.days_overdue,
        }
    rate = rate_for(company=loan.company, as_of=when)
    nio_part = loan.credit_nio.outstanding_amount if loan.credit_nio else Decimal("0")
    usd_part = loan.credit_usd.outstanding_amount if loan.credit_usd else Decimal("0")
    if usd_part and rate:
        out["consolidated_nio"] = str(_q2(nio_part + usd_part * rate))
        out["rate_used"] = str(rate)
    elif not usd_part:
        out["consolidated_nio"] = str(_q2(nio_part))
    return out


# ---------------------------------------------------------------------------
# F2 — Acopio en custodia → fijación → liquidación
# ---------------------------------------------------------------------------

def _require_acopio_settings(company: OrgUnit) -> FinancingSettings:
    row = get_or_create_settings(company=company)
    if row.coffee_item_id is None or row.custody_warehouse_id is None:
        raise FinancingError(
            "FIN_SETTINGS_INCOMPLETE",
            "Configura el ítem de café y la bodega de custodia antes de acopiar.",
        )
    return row


@transaction.atomic
def receive_coffee(
    *, request, actor, producer: ProducerProfile, quality: CoffeeQualityGrade,
    physical_state: str, sacks: int, gross_lb: Decimal, tare_lb: Optional[Decimal] = None,
    reception_date: Optional[date] = None, reference: str = "", note: str = "",
    idempotency_key: str = "",
) -> CoffeeReception:
    """Recepción de acopio EN CUSTODIA (el café sigue siendo del productor)."""
    company: OrgUnit = request.company
    if producer.company_id != company.id:
        raise FinancingError("FIN_PRODUCER_SCOPE", "El productor pertenece a otra empresa.")
    settings_row = _require_acopio_settings(company)
    custody_warehouse = settings_row.custody_warehouse
    custody_warehouse_id = settings_row.custody_warehouse_id
    coffee_item_id = settings_row.coffee_item_id
    if custody_warehouse is None or custody_warehouse_id is None or coffee_item_id is None:
        raise FinancingError(
            "FIN_SETTINGS_INCOMPLETE",
            "Configura el ítem de café y la bodega de custodia antes de acopiar.",
        )
    gross = _q2(Decimal(gross_lb))
    if gross <= 0 or sacks <= 0:
        raise FinancingError("FIN_RECEPTION_INVALID", "Libras brutas y sacos deben ser positivos.")
    tare = _q2(Decimal(tare_lb)) if tare_lb is not None else _q2(gross * quality.default_tare_pct / Decimal("100"))
    if tare < 0 or tare >= gross:
        raise FinancingError("FIN_RECEPTION_INVALID", "La tara debe ser ≥ 0 y menor que el peso bruto.")
    net = _q2(gross - tare)

    reception = CoffeeReception.objects.create(
        company=company, producer=producer, warehouse=custody_warehouse,
        reception_date=reception_date or timezone.localdate(), reference=reference,
        quality=quality, physical_state=physical_state, sacks=sacks,
        gross_lb=gross, tare_lb=tare, net_lb=net, note=note,
        created_by=actor if getattr(actor, "pk", None) else None,
    )
    result = post_receive(
        request=request, actor=actor,
        warehouse_id=custody_warehouse_id, item_id=coffee_item_id,
        qty=net, unit_cost=Decimal("0.00"),  # custodia: aún no es nuestro
        idempotency_key=idempotency_key or f"fin-rcv-{reception.pk}",
        note=f"Acopio custodia recepción #{reception.pk}",
        source_module="FINANCING", source_type="CoffeeReception", source_id=str(reception.pk),
    )
    reception.stock_movement_id = result.movement_id
    reception.save(update_fields=["stock_movement_id"])
    return reception


def producer_deposit_balance(*, producer: ProducerProfile) -> dict[str, str]:
    """Depósito del productor: recibido − fijado = disponible para fijar;
    recibido − liquidado = café físico aún en custodia."""
    from django.db.models import Sum

    received = producer.receptions.aggregate(s=Sum("net_lb"))["s"] or Decimal("0")
    fixed = producer.fixations.aggregate(s=Sum("pounds"))["s"] or Decimal("0")
    liquidated = (
        producer.fixations.filter(status=FixationStatus.LIQUIDATED).aggregate(s=Sum("pounds"))["s"]
        or Decimal("0")
    )
    return {
        "received_lb": str(_q2(received)),
        "fixed_lb": str(_q2(fixed)),
        "available_lb": str(_q2(received - fixed)),
        "in_custody_lb": str(_q2(received - liquidated)),
    }


def fix_price(
    *, company: OrgUnit, producer: ProducerProfile, pounds: Decimal, price_per_lb: Decimal,
    currency: str = Currency.USD, fixation_date: Optional[date] = None, note: str = "",
    actor=None,
) -> PriceFixation:
    """Fija precio para X libras del depósito disponible del productor."""
    if producer.company_id != company.id:
        raise FinancingError("FIN_PRODUCER_SCOPE", "El productor pertenece a otra empresa.")
    pounds = _q2(Decimal(pounds))
    price = Decimal(price_per_lb)
    if pounds <= 0 or price <= 0:
        raise FinancingError("FIN_FIXATION_INVALID", "Libras y precio deben ser positivos.")
    available = Decimal(producer_deposit_balance(producer=producer)["available_lb"])
    if pounds > available:
        raise FinancingError(
            "FIN_DEPOSIT_INSUFFICIENT",
            f"El productor solo tiene {available} lb disponibles en depósito (pidió fijar {pounds}).",
        )
    return PriceFixation.objects.create(
        company=company, producer=producer, fixation_date=fixation_date or timezone.localdate(),
        pounds=pounds, price_per_lb=price, currency=currency, note=note,
        created_by=actor if getattr(actor, "pk", None) else None,
    )


@transaction.atomic
def liquidate(
    *, request, actor, producer: ProducerProfile, fixation_ids: list[int],
    loan: Optional[FinancingLoan] = None, deductions: Optional[list[dict]] = None,
    liquidation_date: Optional[date] = None, exchange_rate: Optional[Decimal] = None,
    note: str = "",
) -> Liquidation:
    """Liquidación F8 del SIFA: compra el café fijado y abona el préstamo en un acto."""
    company: OrgUnit = request.company
    if producer.company_id != company.id:
        raise FinancingError("FIN_PRODUCER_SCOPE", "El productor pertenece a otra empresa.")
    settings_row = _require_acopio_settings(company)
    custody_warehouse_id = settings_row.custody_warehouse_id
    liquidation_warehouse_id = settings_row.liquidation_warehouse_id
    coffee_item_id = settings_row.coffee_item_id
    if custody_warehouse_id is None or liquidation_warehouse_id is None or coffee_item_id is None:
        raise FinancingError(
            "FIN_SETTINGS_INCOMPLETE", "Configura la bodega propia de liquidación.",
        )
    when = liquidation_date or timezone.localdate()

    fixations = list(
        PriceFixation.objects.select_for_update()
        .filter(pk__in=fixation_ids, company=company, producer=producer)
    )
    if len(fixations) != len(set(fixation_ids)) or not fixations:
        raise FinancingError("FIN_FIXATION_NOT_FOUND", "Alguna fijación no existe o no es del productor.")
    if any(f.status != FixationStatus.OPEN for f in fixations):
        raise FinancingError("FIN_FIXATION_STATE", "Alguna fijación ya fue liquidada.")
    currencies = {f.currency for f in fixations}
    if len(currencies) != 1:
        raise FinancingError("FIN_FIXATION_MIXED", "No se pueden mezclar monedas en una liquidación.")
    currency = currencies.pop()

    pounds_total = _q2(sum((f.pounds for f in fixations), Decimal("0")))
    gross = _q2(sum((f.pounds * f.price_per_lb for f in fixations), Decimal("0")))

    deductions = deductions or []
    for d in deductions:
        if Decimal(d.get("amount", "0")) <= 0 or not str(d.get("concept", "")).strip():
            raise FinancingError("FIN_DEDUCTION_INVALID", "Cada retención requiere concepto y monto positivo.")
    deductions_total = _q2(sum((Decimal(d["amount"]) for d in deductions), Decimal("0")))
    if deductions_total > gross:
        raise FinancingError("FIN_DEDUCTION_EXCEEDS", "Las retenciones exceden el valor bruto.")
    net = _q2(gross - deductions_total)

    # Tasa: obligatoria para valorar inventario si la fijación es en US$, y para
    # cruzar moneda si el préstamo solo tiene saldo en la otra.
    rate = exchange_rate or rate_for(company=company, as_of=when)
    if currency == Currency.USD and not rate:
        raise FinancingError("FIN_RATE_REQUIRED", "No hay tasa de cambio vigente para valorar la liquidación.")

    liq = Liquidation.objects.create(
        company=company, producer=producer, loan=loan, liquidation_date=when,
        currency=currency, pounds_total=pounds_total, gross_value=gross,
        deductions_total=deductions_total, exchange_rate_used=rate, note=note,
        created_by=actor if getattr(actor, "pk", None) else None,
    )
    for d in deductions:
        LiquidationDeduction.objects.create(
            liquidation=liq, concept=str(d["concept"])[:120], amount=_q2(Decimal(d["amount"])),
        )

    # 1) Abono al préstamo (si hay préstamo y valor neto).
    applied = Decimal("0.00")
    applied_ccy = ""
    if loan is not None and net > 0:
        if loan.company_id != company.id or loan.producer_id != producer.pk:
            raise FinancingError("FIN_LOAN_SCOPE", "El préstamo no corresponde al productor/empresa.")
        credit = loan.credit_for(currency)
        cross = False
        if credit is None or credit.outstanding_amount <= 0:
            other = Currency.USD if currency == Currency.NIO else Currency.NIO
            credit = loan.credit_for(other)
            cross = credit is not None and credit.outstanding_amount > 0
            if not cross:
                credit = None
        if credit is not None:
            allocation_rate: Optional[Decimal] = None
            if cross:
                if rate is None:
                    raise FinancingError("FIN_RATE_REQUIRED", "Se necesita tasa para abonar el saldo en otra moneda.")
                allocation_rate = rate
                net_in_credit_ccy = _q2(net / rate) if credit.currency == Currency.USD else _q2(net * rate)
            else:
                net_in_credit_ccy = net
            applied = min(net_in_credit_ccy, credit.outstanding_amount)
            applied_ccy = credit.currency
            intent, _idem = create_payment_intent_for_scope(
                company=company, branch=request.branch, actor=actor, request=request,
                amount=applied, currency=credit.currency,
                idempotency_key=f"fin-liq-{liq.pk}",
                payment_method=TenderPaymentMethod.COFFEE_QUOTA,
            )
            intent = capture_payment_intent_for_scope(
                company=company, branch=request.branch, actor=actor,
                payment_id=intent.payment_id, request=request,
            )
            allocate_payment_to_obligation(
                intent, credit, applied, when, actor,
                exchange_rate=allocation_rate,
            )
            credit.refresh_from_db()
            liq.payment_intent_id = intent.payment_id
            _refresh_loan_status(loan)

    # 2) Excedente a favor del productor (CxP).
    if applied_ccy and applied_ccy != currency:
        if rate is None:
            raise FinancingError("FIN_RATE_REQUIRED", "Se necesita tasa para convertir el abono aplicado.")
        applied_in_liq_ccy = _q2(applied * rate) if applied_ccy == Currency.USD else _q2(applied / rate)
    else:
        applied_in_liq_ccy = applied
    surplus = _q2(net - applied_in_liq_ccy)
    if surplus > 0:
        payable = create_payable(
            company=company, party=producer.party,
            reference_type="FINANCING_LIQUIDATION", reference_id=liq.pk,
            principal_amount=surplus, currency=currency,
            issue_date=when, due_date=when,
            created_by=actor if getattr(actor, "pk", None) else None,
            metadata={"liquidation_id": liq.pk},
        )
        liq.payable = payable

    # 3) El café deja la custodia y entra al inventario propio con costo de compra.
    if currency == Currency.NIO:
        cost_nio_total = gross
    else:
        if rate is None:
            raise FinancingError("FIN_RATE_REQUIRED", "No hay tasa de cambio vigente para valorar la liquidación.")
        cost_nio_total = _q2(gross * rate)
    unit_cost = (cost_nio_total / pounds_total).quantize(Decimal("0.0001"), rounding=ROUND_HALF_UP)
    issue = post_issue(
        request=request, actor=actor,
        warehouse_id=custody_warehouse_id, item_id=coffee_item_id,
        qty=pounds_total, idempotency_key=f"fin-liq-out-{liq.pk}",
        note=f"Liquidación #{liq.pk}: sale de custodia",
        source_module="FINANCING", source_type="Liquidation", source_id=str(liq.pk),
    )
    receive = post_receive(
        request=request, actor=actor,
        warehouse_id=liquidation_warehouse_id, item_id=coffee_item_id,
        qty=pounds_total, unit_cost=unit_cost,
        idempotency_key=f"fin-liq-in-{liq.pk}",
        note=f"Liquidación #{liq.pk}: compra de café acopiado",
        source_module="FINANCING", source_type="Liquidation", source_id=str(liq.pk),
    )

    liq.applied_to_loan = applied
    liq.applied_currency = applied_ccy
    liq.surplus_amount = surplus
    liq.custody_issue_movement_id = issue.movement_id
    liq.own_receive_movement_id = receive.movement_id
    liq.save(update_fields=[
        "applied_to_loan", "applied_currency", "surplus_amount", "payment_intent_id",
        "payable", "custody_issue_movement_id", "own_receive_movement_id",
    ])
    PriceFixation.objects.filter(pk__in=[f.pk for f in fixations]).update(
        status=FixationStatus.LIQUIDATED, liquidation=liq,
    )

    publish_outbox_event(
        request=request, source_module="FINANCING", event_type="CoffeeLiquidated",
        payload={
            "liquidation_id": liq.pk, "producer_id": producer.pk,
            "loan_id": loan.pk if loan else None,
            "pounds": str(pounds_total), "gross_value": str(gross), "currency": currency,
            "applied_to_loan": str(applied), "surplus": str(surplus),
        },
        actor_user=actor, company=company, branch=getattr(request, "branch", None),
    )
    write_event(
        request=request, event_type="FINANCING_LIQUIDATION_CREATED",
        actor_user=actor, subject_type="FINANCING_LIQUIDATION", subject_id=str(liq.pk),
        module="financiamiento",
        metadata={"gross": str(gross), "applied": str(applied), "surplus": str(surplus)},
    )
    return liq
