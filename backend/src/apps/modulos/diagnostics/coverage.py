"""Cobertura por línea desde `coverage.xml` — *¿la línea que falló está testeada?* (sin IA).

Parsea el reporte Cobertura que ya genera la suite (`qa/reports/coverage.xml`) a un mapa
`{path_normalizado: {línea: hits}}`. La normalización recorta a `apps/...` para que matchee
con `ErrorEvent.file_path` sin importar el prefijo del entorno. Solo parsea nuestro propio
reporte (confiable), no entrada externa.
"""
from __future__ import annotations

# Solo parsea nuestro propio coverage.xml (generado por la suite), no entrada externa:
# XXE/entity-expansion no aplican. Por eso se suprime el aviso de bandit (B405/B314).
import xml.etree.ElementTree as ET  # nosec B405


def _norm(path: str) -> str:
    p = (path or "").replace("\\", "/")
    idx = p.find("apps/")
    return p[idx:] if idx >= 0 else p


def parse_coverage_xml(xml_text: str) -> dict[str, dict[int, int]]:
    out: dict[str, dict[int, int]] = {}
    if not xml_text.strip():
        return out
    try:
        root = ET.fromstring(xml_text)  # nosec B314
    except ET.ParseError:
        return out
    for cls in root.iter("class"):
        key = _norm(cls.get("filename") or "")
        if not key:
            continue
        lines = out.setdefault(key, {})
        for line in cls.iter("line"):
            try:
                num = int(line.get("number") or "")
                hits = int(line.get("hits") or "0")
            except (TypeError, ValueError):
                continue
            lines[num] = hits
    return out


def coverage_state_for_line(cov_map: dict[str, dict[int, int]], path: str, line: int) -> str:
    """`covered` | `uncovered` | `unknown` (archivo/línea no medida)."""
    file_lines = cov_map.get(_norm(path))
    if not file_lines or line not in file_lines:
        return "unknown"
    return "covered" if file_lines[line] > 0 else "uncovered"
