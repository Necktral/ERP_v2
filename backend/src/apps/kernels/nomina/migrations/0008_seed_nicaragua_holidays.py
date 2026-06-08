from __future__ import annotations

from django.db import migrations

# Precarga del catálogo nacional de feriados de Nicaragua (company = NULL = compartido).
# Tres ejes: legal_type (cómo paga / si obliga al privado), date_kind (recurrencia),
# applies_to_payroll (si por defecto cuenta para la planilla).
#
# NOTA: lista de arranque. La lista legal exacta (Código del Trabajo art. 66 + asuetos
# vigentes) debe confirmarse con el contador/MITRAB; el seed es idempotente (get_or_create
# por code) para poder ajustarlo. Geografía GENERAL: locality es informativo; el revisor
# de la planilla ubica los días que aplican.

# (code, name, legal_type, date_kind, month, day, easter_offset, locality,
#  applies_to_payroll, pays_premium)
NI_HOLIDAYS = [
    # --- Nacionales obligatorios (Código del Trabajo) ---
    ("ni-ano-nuevo", "Año Nuevo", "NACIONAL_OBLIGATORIO", "FIXED", 1, 1, None, "Nacional", True, True),
    ("ni-jueves-santo", "Jueves Santo", "NACIONAL_OBLIGATORIO", "EASTER", None, None, -3, "Nacional", True, True),
    ("ni-viernes-santo", "Viernes Santo", "NACIONAL_OBLIGATORIO", "EASTER", None, None, -2, "Nacional", True, True),
    ("ni-dia-trabajo", "Día Internacional del Trabajo", "NACIONAL_OBLIGATORIO", "FIXED", 5, 1, None, "Nacional", True, True),
    ("ni-revolucion", "Día de la Revolución", "NACIONAL_OBLIGATORIO", "FIXED", 7, 19, None, "Nacional", True, True),
    ("ni-san-jacinto", "Batalla de San Jacinto", "NACIONAL_OBLIGATORIO", "FIXED", 9, 14, None, "Nacional", True, True),
    ("ni-independencia", "Independencia de Centroamérica", "NACIONAL_OBLIGATORIO", "FIXED", 9, 15, None, "Nacional", True, True),
    ("ni-purisima", "La Purísima (Concepción de María)", "NACIONAL_OBLIGATORIO", "FIXED", 12, 8, None, "Nacional", True, True),
    ("ni-navidad", "Navidad", "NACIONAL_OBLIGATORIO", "FIXED", 12, 25, None, "Nacional", True, True),
    # --- Locales / fiestas patronales (el revisor ubica si aplica a la finca) ---
    ("ni-santo-domingo-bajada", "Santo Domingo de Guzmán (bajada)", "LOCAL", "FIXED", 8, 1, None, "Managua", True, True),
    ("ni-santo-domingo-subida", "Santo Domingo de Guzmán (subida)", "LOCAL", "FIXED", 8, 10, None, "Managua", True, True),
    # --- Asuetos estatales (sector público; no obligan al privado) ---
    ("ni-difuntos", "Día de los Difuntos", "ASUETO_ESTATAL", "FIXED", 11, 2, None, "Nacional (sector público)", False, False),
]


def seed_holidays(apps, schema_editor):
    Holiday = apps.get_model("nomina", "Holiday")
    for (code, name, legal_type, date_kind, month, day, easter_offset,
         locality, applies_to_payroll, pays_premium) in NI_HOLIDAYS:
        Holiday.objects.get_or_create(
            company=None,
            code=code,
            defaults={
                "name": name,
                "legal_type": legal_type,
                "date_kind": date_kind,
                "month": month,
                "day": day,
                "easter_offset": easter_offset,
                "locality": locality,
                "applies_to_payroll": applies_to_payroll,
                "pays_premium": pays_premium,
                "is_active": True,
            },
        )


def unseed_holidays(apps, schema_editor):
    Holiday = apps.get_model("nomina", "Holiday")
    codes = [row[0] for row in NI_HOLIDAYS]
    Holiday.objects.filter(company__isnull=True, code__in=codes).delete()


class Migration(migrations.Migration):

    dependencies = [
        ("nomina", "0007_holiday"),
    ]

    operations = [
        migrations.RunPython(seed_holidays, unseed_holidays),
    ]
