"""Seed del catálogo estándar de reglas SoD (globales, company=NULL).

Idempotente por `code`. Severidades sugeridas; ajustables con control interno /
contador. `event_a`/`event_b` se rellenan solo donde existe un event_type del
audit log que evidencie el ejercicio (habilita el detector SOD_EXERCISED).
"""
from django.db import migrations

# code, name, perm_a, perm_b, event_a, event_b, severity, rationale
_RULES = [
    (
        "ghost_employee",
        "Empleado fantasma",
        "hr.employee.create",
        "nomina.period.approve",
        "HR_EMPLOYEE_CREATED",
        "NOMINA_PERIOD_APPROVED",
        "CRITICAL",
        "Quien crea empleados no debe aprobar la planilla (riesgo de empleado fantasma).",
    ),
    (
        "invoice_create_void",
        "Emitir y anular facturas",
        "billing.invoice.create",
        "billing.invoice.void",
        "BILLING_INVOICE_CREATED",
        "BILLING_INVOICE_VOIDED",
        "HIGH",
        "Quien crea facturas no debe poder anularlas (ocultar ventas/desvío).",
    ),
    (
        "payment_create_refund",
        "Crear pagos y aprobar reembolsos",
        "payments.intent.create",
        "payments.refund.approve",
        "",
        "",
        "HIGH",
        "Quien registra cobros no debe aprobar sus reembolsos (desvío de fondos).",
    ),
    (
        "procurement_create_post",
        "Crear y mayorizar compras",
        "procurement.doc.create",
        "procurement.doc.post",
        "",
        "",
        "HIGH",
        "Quien crea documentos de compra no debe mayorizarlos (compras ficticias).",
    ),
    (
        "field_capture_approve",
        "Capturar y aprobar asistencia de campo",
        "nomina.field.capture",
        "nomina.field.approve",
        "",
        "",
        "MEDIUM",
        "Refuerzo de la regla maker-checker: el capturador no debe aprobar la asistencia.",
    ),
    (
        "self_grant_power",
        "Autoconcederse poderes",
        "rbac.assignments.update",
        "org.company.create",
        "",
        "",
        "CRITICAL",
        "Quien administra asignaciones de roles no debe poder crear empresas (acumulación de poder).",
    ),
]


def seed(apps, schema_editor):
    SegregationRule = apps.get_model("controls", "SegregationRule")
    for code, name, pa, pb, ea, eb, sev, rationale in _RULES:
        SegregationRule.objects.get_or_create(
            company=None,
            code=code,
            defaults={
                "name": name,
                "permission_a": pa,
                "permission_b": pb,
                "event_a": ea,
                "event_b": eb,
                "severity": sev,
                "rationale": rationale,
                "is_active": True,
            },
        )


def unseed(apps, schema_editor):
    SegregationRule = apps.get_model("controls", "SegregationRule")
    SegregationRule.objects.filter(company__isnull=True, code__in=[r[0] for r in _RULES]).delete()


class Migration(migrations.Migration):

    dependencies = [
        ("controls", "0001_initial"),
    ]

    operations = [
        migrations.RunPython(seed, unseed),
    ]
