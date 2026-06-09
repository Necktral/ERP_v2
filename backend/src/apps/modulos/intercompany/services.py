"""Orquestación de operaciones intercompany del grupo (seam de consolidación).

Una operación entre dos empresas del grupo (la empresa A le cobra/suministra a la B)
dispara **todas** sus patas con una **referencia común**, reusando la maquinaria que ya
existe — NO reimplementa contabilidad ni consolidación:

  * pata GL en cada empresa (asiento posteado),
  * **CxC** en A (party = empresa B, `INTERNAL`) + **CxP** en B (party = empresa A),
  * enlace `IntercompanyTransaction` (source/target journal entries) + confirm,

de modo que `accounting.phase7b.run_consolidation` **elimina** el intercompany (el grupo
no se infla). Es el primitivo que reutilizarán los verticales (comisariato, transporte,
ganado): cuando una operación cruza empresas, llama a `record_intercompany_charge`.

Requiere **autorización explícita** entre empresas (`CompanyLink` + `LinkGrant`
`accounting.intercompany.write`): "independientes pero interrelacionadas".

Edges: `modulos.intercompany -> {kernels.accounting, kernels.portfolio, modulos.parties,
modulos.audit, modulos.iam, modulos.common}`.
"""
from __future__ import annotations

from datetime import datetime, timedelta
from decimal import Decimal
from typing import Any

from django.db import transaction
from django.db.models import Sum
from django.utils import timezone

from apps.kernels.accounting.models import (
    ChartOfAccount,
    EconomicEvent,
    FiscalPeriod,
    IntercompanyTransaction,
    JournalDraft,
    JournalEntry,
    JournalEntryLine,
    PostingRuleSet,
)
from apps.kernels.accounting.phase7b import (
    confirm_intercompany_transaction,
    create_intercompany_transaction,
)
from apps.kernels.portfolio.models import Payable, Receivable
from apps.kernels.portfolio.services import create_payable, create_receivable
from apps.modulos.audit.writer import write_event
from apps.modulos.iam.models import OrgUnit
from apps.modulos.iam.selectors import has_intercompany_grant
from apps.modulos.parties.models import Party
from apps.modulos.parties.services import create_party

INTERCOMPANY_WRITE = "accounting.intercompany.write"

# Cuentas por defecto (ajustables con el contador); deben existir en el CoA de cada empresa.
IC_RECEIVABLE = "1301"  # CxC intercompañía (activo) — la que cobra
IC_REVENUE = "4101"     # Ingreso intercompañía — la que cobra
IC_EXPENSE = "5101"     # Gasto/Costo intercompañía — la que paga
IC_PAYABLE = "2109"     # CxP intercompañía (pasivo) — la que paga

CENT = Decimal("0.01")


def _q(value) -> Decimal:
    return Decimal(str(value if value is not None else 0)).quantize(CENT)


def _company(company_id: int) -> OrgUnit:
    c = OrgUnit.objects.filter(id=company_id, unit_type=OrgUnit.UnitType.COMPANY).first()
    if c is None:
        raise ValueError(f"COMPANY {company_id} no encontrada.")
    return c


def _hq_branch(company: OrgUnit) -> OrgUnit | None:
    return (
        OrgUnit.objects.filter(parent=company, unit_type=OrgUnit.UnitType.BRANCH, is_active=True)
        .order_by("id")
        .first()
    )


def party_for_company(*, in_company: OrgUnit, of_company: OrgUnit, actor=None) -> Party:
    """Party `INTERNAL` en los libros de `in_company` que representa a `of_company`."""
    existing = Party.objects.filter(
        company=in_company, party_type=Party.PartyType.INTERNAL, display_name=of_company.name
    ).first()
    if existing is not None:
        return existing
    return create_party(
        company=in_company,
        party_type=Party.PartyType.INTERNAL,
        display_name=of_company.name,
        legal_name=of_company.name,
        actor=actor,
    )


def _rule_set(company: OrgUnit) -> PostingRuleSet:
    """RuleSet estable por empresa para los asientos intercompany (provenance)."""
    rs, _ = PostingRuleSet.objects.get_or_create(
        code=f"intercompany_manual_c{company.id}",
        version=1,
        defaults={
            "status": PostingRuleSet.Status.ACTIVE,
            "fiscal_mode": PostingRuleSet.FiscalMode.BOTH,
            "scope_company": company,
            "rules_json": {"version": "1.0", "rules": []},
        },
    )
    return rs


def _post_balanced_entry(*, company, branch, when: datetime, lines, description, actor) -> JournalEntry:
    """Postea un asiento balanceado (sistema) y devuelve el JournalEntry.

    `lines`: lista de (account_code, side DEBIT|CREDIT, amount). Mismo patrón probado en
    `tests/test_phase7b_intercompany_consolidation.py::_post_entry`.

    I-01 (decisión de diseño, deliberada): este asiento de eliminación/cruce
    intercompany se crea **directo en estado POSTED**, sin pasar por el maker-checker
    del GL (`approve_journal_drafts`/`post_journal_drafts`). Es un asiento **generado
    por el sistema** (no un asiento manual de un usuario): siempre balanceado, derivado
    de un cruce ya autorizado en la capa operativa. Es coherente con el auto-post de
    `link_operational_event_to_accounting` (ver AC-01): el control SoD vive en la
    operación que origina el cruce, no en el posteo derivado. NO exponer este camino
    como endpoint de posteo manual.
    """
    debit = _q(sum((a for _, s, a in lines if s == "DEBIT"), Decimal("0")))
    credit = _q(sum((a for _, s, a in lines if s == "CREDIT"), Decimal("0")))
    if debit != credit:
        raise ValueError("Asiento intercompany no balanceado.")
    period, _ = FiscalPeriod.objects.get_or_create(
        company=company, year=when.year, month=when.month,
        defaults={"status": FiscalPeriod.Status.OPEN},
    )
    event = EconomicEvent.objects.create(
        source_module="INTERCOMPANY",
        event_type="IntercompanyCharge",
        company=company,
        branch=branch,
        occurred_at=when,
        payload={"description": description},
    )
    draft = JournalDraft.objects.create(
        economic_event=event,
        rule_set=_rule_set(company),
        state=JournalDraft.State.POSTED,
        total_debit=debit,
        total_credit=credit,
        lines_json=[{"account": c, "side": s, "amount": str(_q(a))} for c, s, a in lines],
    )
    entry = JournalEntry.objects.create(
        draft=draft,
        period=period,
        company=company,
        branch=branch,
        entry_date=when.date(),
        description=description[:255],
        debit_total=debit,
        credit_total=credit,
        posted_by=actor,
    )
    for i, (code, side, amt) in enumerate(lines, start=1):
        account = ChartOfAccount.objects.filter(company=company, code=code).first()
        if account is None:
            raise ValueError(f"Cuenta {code} no existe en el CoA de la empresa {company.id}.")
        JournalEntryLine.objects.create(
            journal_entry=entry,
            line_no=i,
            account=account,
            account_code_snapshot=code,
            currency="NIO",
            fx_rate=Decimal("1.00000000"),
            amount_tx=_q(amt),
            debit_base=_q(amt) if side == "DEBIT" else Decimal("0.00"),
            credit_base=_q(amt) if side == "CREDIT" else Decimal("0.00"),
        )
    return entry


def _bundle(tx: IntercompanyTransaction) -> dict[str, Any]:
    md = dict(tx.metadata_json or {})
    return {
        "tx_id": str(tx.tx_id),
        "status": tx.status,
        "amount": str(tx.amount),
        "source_company_id": tx.source_company_id,
        "target_company_id": tx.target_company_id,
        "source_journal_entry_id": tx.source_journal_entry_id,
        "target_journal_entry_id": tx.target_journal_entry_id,
        "receivable_id": md.get("receivable_id"),
        "payable_id": md.get("payable_id"),
        "reference_code": tx.reference_code,
    }


@transaction.atomic
def record_intercompany_charge(
    *,
    source_company_id: int,
    target_company_id: int,
    amount,
    reference_code: str,
    concept: str = "",
    effective_date=None,
    currency: str = "NIO",
    actor=None,
) -> dict[str, Any]:
    """Registra una operación intercompany completa (A cobra a B). Idempotente por `reference_code`.

    Crea: pata GL en A (DEBE 1301 / HABER 4101) y en B (DEBE 5101 / HABER 2109), CxC en A,
    CxP en B, y enlaza+confirma el `IntercompanyTransaction` (cuentas P&L para que la
    consolidación elimine). Todo en una transacción: si falla algo, no deja estado parcial.
    """
    if not str(reference_code or "").strip():
        raise ValueError("reference_code es requerido (idempotencia).")
    source = _company(source_company_id)
    target = _company(target_company_id)
    if source.id == target.id:
        raise ValueError("source y target deben ser empresas distintas.")
    money = _q(amount)
    if money <= Decimal("0.00"):
        raise ValueError("amount debe ser > 0.")

    existing = IntercompanyTransaction.objects.filter(
        source_company=source, target_company=target, reference_code=reference_code
    ).first()
    if existing is not None:
        return _bundle(existing)

    # Autorización explícita entre empresas (independientes pero interrelacionadas).
    if not has_intercompany_grant(
        from_company=target, to_company=source,
        permission_code=INTERCOMPANY_WRITE, mode="WRITE", scope_branch=None,
    ):
        raise ValueError("INTERCOMPANY_NOT_AUTHORIZED")

    base_date = effective_date or timezone.localdate()
    when = datetime.combine(base_date, datetime.min.time())
    if timezone.is_naive(when):
        when = timezone.make_aware(when)

    source_entry = _post_balanced_entry(
        company=source, branch=_hq_branch(source), when=when,
        lines=[(IC_RECEIVABLE, "DEBIT", money), (IC_REVENUE, "CREDIT", money)],
        description=f"IC cobro a {target.name}: {concept}", actor=actor,
    )
    target_entry = _post_balanced_entry(
        company=target, branch=_hq_branch(target), when=when,
        lines=[(IC_EXPENSE, "DEBIT", money), (IC_PAYABLE, "CREDIT", money)],
        description=f"IC pago a {source.name}: {concept}", actor=actor,
    )

    tx = create_intercompany_transaction(
        source_company_id=source.id,
        target_company_id=target.id,
        amount=money,
        currency=currency,
        source_account_code=IC_REVENUE,
        target_account_code=IC_EXPENSE,
        source_side=IntercompanyTransaction.Side.CREDIT,
        target_side=IntercompanyTransaction.Side.DEBIT,
        source_journal_entry_id=source_entry.id,
        target_journal_entry_id=target_entry.id,
        reference_code=reference_code,
        effective_at=when,
        actor_user=actor,
    )
    confirm_intercompany_transaction(tx_id=str(tx.tx_id), actor_user=actor, allow_same_actor=True)

    issue = when.date()
    due = issue + timedelta(days=30)
    rec = create_receivable(
        company=source,
        party=party_for_company(in_company=source, of_company=target, actor=actor),
        reference_type="INTERCOMPANY",
        reference_id=int(tx.id),
        principal_amount=money,
        currency=currency,
        issue_date=issue,
        due_date=due,
        branch=_hq_branch(source),
        created_by=actor,
    )
    pay = create_payable(
        company=target,
        party=party_for_company(in_company=target, of_company=source, actor=actor),
        reference_type="INTERCOMPANY",
        reference_id=int(tx.id),
        principal_amount=money,
        currency=currency,
        issue_date=issue,
        due_date=due,
        branch=_hq_branch(target),
        created_by=actor,
    )

    tx.refresh_from_db()
    md = dict(tx.metadata_json or {})
    md.update({"receivable_id": rec.id, "payable_id": pay.id, "concept": concept})
    tx.metadata_json = md
    tx.save(update_fields=["metadata_json", "updated_at"])

    write_event(
        request=None,
        module="INTERCOMPANY",
        event_type="INTERCOMPANY_CHARGE_RECORDED",
        reason_code="OK",
        actor_user=actor,
        subject_type="INTERCOMPANY_TX",
        subject_id=str(tx.tx_id),
        metadata={
            "source_company_id": source.id,
            "target_company_id": target.id,
            "amount": str(money),
            "reference_code": reference_code,
            "receivable_id": rec.id,
            "payable_id": pay.id,
        },
    )
    return _bundle(tx)


def group_cartera_position(*, company_ids: list[int]) -> dict[str, Any]:
    """Posición de cartera del grupo por empresa, separando intercompany (party `INTERNAL`)."""
    def _sum(model, company_id: int, internal: bool) -> Decimal:
        qs = model.objects.filter(company_id=company_id)
        qs = (
            qs.filter(party__party_type=Party.PartyType.INTERNAL)
            if internal
            else qs.exclude(party__party_type=Party.PartyType.INTERNAL)
        )
        return _q(qs.aggregate(s=Sum("principal_amount"))["s"] or 0)

    by_company = []
    for cid in company_ids:
        by_company.append({
            "company_id": int(cid),
            "cxc_external": str(_sum(Receivable, cid, False)),
            "cxc_intercompany": str(_sum(Receivable, cid, True)),
            "cxp_external": str(_sum(Payable, cid, False)),
            "cxp_intercompany": str(_sum(Payable, cid, True)),
        })
    return {"by_company": by_company}
