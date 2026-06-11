"""Siembra los puestos agrícolas v0.1 (JobPosition + PositionRoleMap) para una empresa.

Idempotente. Habilitar/deshabilitar por flags: `--disable`/`--enable`/`--only` (códigos CSV del
catálogo). En re-corridas NO pisa el `is_active` de un puesto que no esté nombrado por un flag.
No crea empleados ni nómina. Requiere que `seed_rbac_v01` ya haya sembrado los roles.
"""
from __future__ import annotations

import json
from dataclasses import asdict

from django.core.management.base import BaseCommand, CommandError

from apps.modulos.hr.seed_positions_v01 import POSITION_CATALOG, seed_hr_positions_v01
from apps.modulos.iam.models import OrgUnit


def _csv(value: str | None) -> list[str]:
    if not value:
        return []
    return [c.strip() for c in value.split(",") if c.strip()]


class Command(BaseCommand):
    help = "Siembra los puestos agrícolas v0.1 (JobPosition + PositionRoleMap) para una empresa."

    def add_arguments(self, parser):
        parser.add_argument("--company-code", required=True, help="code del OrgUnit COMPANY.")
        parser.add_argument("--disable", default="", help="Códigos CSV a dejar inactivos.")
        parser.add_argument("--enable", default="", help="Códigos CSV a forzar activos.")
        parser.add_argument("--only", default="", help="Restringe el seed a estos códigos CSV.")
        parser.add_argument("--json", action="store_true", help="Salida JSON para máquinas.")

    def handle(self, *args, **options):
        code = (options["company_code"] or "").strip()
        company = (
            OrgUnit.objects.filter(unit_type=OrgUnit.UnitType.COMPANY, code=code)
            .order_by("id")
            .first()
        )
        if company is None:
            raise CommandError(f"No existe OrgUnit COMPANY con code='{code}'.")

        valid_codes = {s.code for s in POSITION_CATALOG}
        requested = set(_csv(options["disable"]) + _csv(options["enable"]) + _csv(options["only"]))
        unknown = sorted(requested - valid_codes)
        if unknown:
            raise CommandError(f"Códigos desconocidos (no están en el catálogo): {unknown}")

        try:
            result = seed_hr_positions_v01(
                company,
                disable_codes=_csv(options["disable"]),
                enable_codes=_csv(options["enable"]),
                only_codes=_csv(options["only"]),
            )
        except ValueError as exc:
            raise CommandError(str(exc)) from exc

        payload = asdict(result)
        if options["json"]:
            self.stdout.write(json.dumps(payload, ensure_ascii=False))
            return

        self.stdout.write(
            self.style.SUCCESS(f"seed_hr_positions_v01: empresa={company.name} code={code}")
        )
        self.stdout.write(
            f"  created={payload['created']} updated={payload['updated']} "
            f"disabled={payload['disabled']} activated={payload['activated']} "
            f"maps_created={payload['maps_created']} skipped={payload['skipped']}"
        )
