"""Corre los detectores de control y materializa hallazgos.

Uso:
    python manage.py run_control_detectors [--company <id>] [--window 90]

Sin --company recorre todas las empresas activas. Pensado para cron (Fase 2).
"""
from __future__ import annotations

from django.core.management.base import BaseCommand

from apps.modulos.iam.models import OrgUnit

from ...services import DEFAULT_WINDOW_DAYS, run_detectors


class Command(BaseCommand):
    help = "Corre los detectores SoD (concesión + ejercicio) y materializa hallazgos."

    def add_arguments(self, parser):
        parser.add_argument("--company", type=int, default=None, help="ID de la empresa (COMPANY).")
        parser.add_argument("--window", type=int, default=DEFAULT_WINDOW_DAYS, help="Ventana en días.")

    def handle(self, *args, **options):
        company_id = options["company"]
        window = options["window"]
        companies = OrgUnit.objects.filter(unit_type=OrgUnit.UnitType.COMPANY, is_active=True)
        if company_id is not None:
            companies = companies.filter(id=company_id)

        total = 0
        for company in companies:
            created = run_detectors(company, window_days=window)
            total += len(created)
            self.stdout.write(f"company={company.id} nuevos_hallazgos={len(created)}")
        self.stdout.write(self.style.SUCCESS(f"Total hallazgos nuevos: {total}"))
