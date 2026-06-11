"""Ingesta de `CodeUnitEvidence`: ata cada línea que falló a su cobertura (sin IA).

Solo las líneas relevantes (donde hay un `ErrorEvent` o un `SecurityFinding`) se anotan con
su estado de cobertura + refs cruzadas. Determinista; alimenta el *por qué* del diagnóstico.
"""
from __future__ import annotations

from typing import Any

from django.utils import timezone

from .coverage import coverage_state_for_line
from .models import CodeUnitEvidence, ErrorEvent, SecurityFinding


def ingest_code_evidence(
    *, cov_map: dict[str, dict[int, int]], now: Any = None
) -> dict[str, int]:
    now = now or timezone.now()

    err_by_loc: dict[tuple[str, int], list[str]] = {}
    sec_by_loc: dict[tuple[str, int], list[str]] = {}
    dom_by_loc: dict[tuple[str, int], str] = {}

    for e in (
        ErrorEvent.objects.exclude(file_path="")
        .filter(line_number__gt=0)
        .values("error_id", "file_path", "line_number", "domain")
    ):
        loc = (str(e["file_path"]), int(e["line_number"]))
        err_by_loc.setdefault(loc, []).append(str(e["error_id"]))
        dom_by_loc.setdefault(loc, str(e["domain"]))

    for f in (
        SecurityFinding.objects.exclude(file_path="")
        .filter(line_start__gt=0)
        .values("finding_id", "file_path", "line_start", "domain")
    ):
        loc = (str(f["file_path"]), int(f["line_start"]))
        sec_by_loc.setdefault(loc, []).append(str(f["finding_id"]))
        dom_by_loc.setdefault(loc, str(f["domain"]))

    created = updated = 0
    for loc in set(err_by_loc) | set(sec_by_loc):
        path, line = loc
        _, was_created = CodeUnitEvidence.objects.update_or_create(
            path=path,
            line_start=line,
            defaults={
                "line_end": line,
                "domain": dom_by_loc.get(loc, ""),
                "coverage_state": coverage_state_for_line(cov_map, path, line),
                "error_refs": err_by_loc.get(loc, []),
                "security_refs": sec_by_loc.get(loc, []),
            },
        )
        if was_created:
            created += 1
        else:
            updated += 1
    return {"created": created, "updated": updated}
