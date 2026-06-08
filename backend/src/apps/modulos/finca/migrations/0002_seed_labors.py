"""Seed del catálogo estándar de labores cafetaleras NI (globales, company=NULL).

Idempotente por `code`. Son **defaults editables**: cada empresa ajusta metas
(`expected_yield`) y tarifas (`default_rate`) con su mandador/contador. La lista
es típica de café en Nicaragua; ampliable.
"""
from django.db import migrations

# code, name, category, unit, is_piecework
_LABORS = [
    ("vivero", "Vivero", "ESTABLECIMIENTO", "JORNAL", False),
    ("trazado_ahoyado", "Trazado y ahoyado", "ESTABLECIMIENTO", "JORNAL", False),
    ("siembra", "Siembra", "ESTABLECIMIENTO", "JORNAL", False),
    ("resiembra", "Resiembra", "ESTABLECIMIENTO", "JORNAL", False),
    ("chapia", "Chapia / deshierba", "MANTENIMIENTO", "JORNAL", False),
    ("control_malezas_quimico", "Control de malezas (químico)", "MANTENIMIENTO", "JORNAL", False),
    ("fertilizacion", "Fertilización / abonado", "MANTENIMIENTO", "JORNAL", False),
    ("poda", "Poda", "MANTENIMIENTO", "JORNAL", False),
    ("regulacion_sombra", "Regulación de sombra", "MANTENIMIENTO", "JORNAL", False),
    ("deschuponado", "Deschuponado", "MANTENIMIENTO", "JORNAL", False),
    ("control_roya", "Control de roya", "SANIDAD", "JORNAL", False),
    ("control_broca", "Control de broca", "SANIDAD", "JORNAL", False),
    ("aplicacion_fitosanitaria", "Aplicación fitosanitaria", "SANIDAD", "JORNAL", False),
    ("corte", "Corte / recolección", "COSECHA", "LATA", True),
    ("repela", "Repela", "COSECHA", "JORNAL", False),
    ("despulpado", "Despulpado", "BENEFICIADO", "JORNAL", False),
    ("lavado", "Lavado", "BENEFICIADO", "JORNAL", False),
    ("secado", "Secado", "BENEFICIADO", "JORNAL", False),
    ("mantenimiento_caminos", "Mantenimiento de caminos", "INFRAESTRUCTURA", "JORNAL", False),
]


def seed(apps, schema_editor):
    Labor = apps.get_model("finca", "Labor")
    for code, name, category, unit, piecework in _LABORS:
        Labor.objects.get_or_create(
            company=None,
            code=code,
            defaults={
                "name": name,
                "category": category,
                "unit": unit,
                "is_piecework": piecework,
                "is_active": True,
            },
        )


def unseed(apps, schema_editor):
    Labor = apps.get_model("finca", "Labor")
    Labor.objects.filter(company__isnull=True, code__in=[r[0] for r in _LABORS]).delete()


class Migration(migrations.Migration):

    dependencies = [
        ("finca", "0001_initial"),
    ]

    operations = [
        migrations.RunPython(seed, unseed),
    ]
