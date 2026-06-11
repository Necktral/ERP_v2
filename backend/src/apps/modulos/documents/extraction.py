"""Extracción DETERMINISTA de campos (IDP F2): texto OCR → borrador estructurado.

Etapa "extraer" del pipeline (captura → OCR → **extraer** → revisión → integración).
Sin IA: regex/heurísticas para los campos de documentos nicaragüenses (RUC, cédula,
fecha, montos, número de documento, placa, galones). Cada campo sale con su confianza
(`high` si hubo etiqueta explícita, `medium`/`low` si fue heurística) y la línea de
evidencia. El resultado es SIEMPRE un borrador: el humano revisa (REVIEWED) antes de
cualquier uso, y esta etapa jamás toca `linked_object_*` ni crea objetos de negocio.

Punto de enchufe para IA: `run_extraction()` es la única puerta de la etapa. Un extractor
LLM (salida estructurada, detrás del kill switch `ai_features_enabled()`) podrá sumarse
aquí cuando el merge train de diagnostics aterrice, sin tocar el flujo ni el contrato.
"""
from __future__ import annotations

import re
from typing import Any

EXTRACTOR_VERSION = "deterministic_v1"

# --- Patrones (tolerantes a ruido de OCR) ----------------------------------------

# RUC jurídico nicaragüense (letra + 13 dígitos) o cédula (000-000000-0000X).
_RUC_LABELED_RE = re.compile(
    r"(?i)\bR\.?\s?U\.?\s?C\.?\s*[:#.]?\s*([A-J]\d{13}|\d{3}-?\d{6}-?\d{4}[A-Z])"
)
_RUC_BARE_RE = re.compile(r"\b[A-J]\d{13}\b")
_CEDULA_RE = re.compile(r"\b\d{3}-\d{6}-\d{4}[A-Z]\b")

_FECHA_LABELED_RE = re.compile(
    r"(?i)\bfecha\b[^\d]{0,12}(\d{1,2}[/-]\d{1,2}[/-]\d{2,4}|\d{4}-\d{2}-\d{2})"
)
_FECHA_BARE_RE = re.compile(r"\b(\d{1,2}[/-]\d{1,2}[/-]\d{4}|\d{4}-\d{2}-\d{2})\b")

# Monto con decimales: 1,234.56 | 1.234,56 | 1234.56 (opcionalmente C$/US$/$ delante).
_MONTO_RE = re.compile(r"(?:C\$|US\$|\$)?\s*(\d{1,3}(?:[.,]\d{3})+[.,]\d{2}|\d+[.,]\d{2})")

_NUMDOC_RE = re.compile(
    r"(?i)\b(?:factura|recibo|ticket|documento)\s*(?:n[oº°.:]*\s*)?[#:]?\s*([A-Z]?[\d][\d-]{3,19})"
)
_PLACA_RE = re.compile(r"(?i)\bplaca\s*[:#.]?\s*([A-Z]{1,2}\s?\d{4,6})")
_GALONES_RE = re.compile(r"(?i)\b(\d+(?:[.,]\d+)?)\s*(?:gal(?:on(?:es)?)?s?|gls?)\b")
_LITROS_RE = re.compile(r"(?i)\b(\d+(?:[.,]\d+)?)\s*(?:litros?|lts?)\b")

# Sugerencia de tipo por palabras clave (solo sugiere; el humano decide en la revisión).
_TYPE_KEYWORDS: tuple[tuple[str, tuple[str, ...]], ...] = (
    ("FUEL_TICKET", ("combustible", "diesel", "diésel", "gasolina", "galones", "bomba")),
    ("PAYROLL", ("planilla", "nómina", "nomina", "salario", "deducciones")),
    ("INVOICE", ("factura", "recibo", "consumidor final", "crédito fiscal")),
)


def _norm_amount(raw: str) -> str:
    """Normaliza '1,234.56' y '1.234,56' a '1234.56' (el separador más a la derecha es el decimal)."""
    s = raw.strip()
    last_dot, last_comma = s.rfind("."), s.rfind(",")
    decimal_sep = "." if last_dot > last_comma else ","
    thousands_sep = "," if decimal_sep == "." else "."
    s = s.replace(thousands_sep, "")
    return s.replace(decimal_sep, ".")


def _line_at(text: str, pos: int) -> str:
    """Línea (recortada) donde cae `pos`, como evidencia mostrable al revisor."""
    start = text.rfind("\n", 0, pos) + 1
    end = text.find("\n", pos)
    if end == -1:
        end = len(text)
    return text[start:end].strip()[:120]


def _field(value: str, confidence: str, evidence: str) -> dict[str, str]:
    return {"value": value, "confidence": confidence, "evidence": evidence}


def _extract_total(text: str) -> dict[str, str] | None:
    """El monto de la línea 'total' (la última, excluyendo 'subtotal'); si no hay
    etiqueta, el monto MAYOR del documento con confianza baja."""
    best: dict[str, str] | None = None
    for line in text.splitlines():
        low = line.lower()
        if "total" not in low or "subtotal" in low or "sub total" in low:
            continue
        m = _MONTO_RE.search(line)
        if m:
            best = _field(_norm_amount(m.group(1)), "high", line.strip()[:120])
    if best is not None:
        return best
    amounts = [(float(_norm_amount(m.group(1))), m) for m in _MONTO_RE.finditer(text)]
    if not amounts:
        return None
    value, m = max(amounts, key=lambda t: t[0])
    return _field(f"{value:.2f}", "low", _line_at(text, m.start()))


def _suggest_doc_type(text: str) -> str:
    low = text.lower()
    for doc_type, keywords in _TYPE_KEYWORDS:
        if any(kw in low for kw in keywords):
            return doc_type
    return ""


def extract_fields(text: str, *, doc_type: str = "") -> dict[str, Any]:
    """Extrae los campos del texto OCR. Determinista: mismo texto → mismo resultado."""
    fields: dict[str, dict[str, str]] = {}

    m = _RUC_LABELED_RE.search(text)
    if m:
        fields["ruc"] = _field(m.group(1).replace("-", ""), "high", _line_at(text, m.start()))
    else:
        m = _RUC_BARE_RE.search(text) or _CEDULA_RE.search(text)
        if m:
            fields["ruc"] = _field(m.group(0).replace("-", ""), "medium", _line_at(text, m.start()))

    m = _FECHA_LABELED_RE.search(text)
    if m:
        fields["fecha"] = _field(m.group(1), "high", _line_at(text, m.start()))
    else:
        m = _FECHA_BARE_RE.search(text)
        if m:
            fields["fecha"] = _field(m.group(1), "medium", _line_at(text, m.start()))

    m = _NUMDOC_RE.search(text)
    if m:
        fields["numero_documento"] = _field(m.group(1), "high", _line_at(text, m.start()))

    total = _extract_total(text)
    if total is not None:
        fields["total"] = total

    if doc_type == "FUEL_TICKET" or not doc_type or doc_type == "GENERAL":
        m = _PLACA_RE.search(text)
        if m:
            fields["placa"] = _field(m.group(1).replace(" ", ""), "high", _line_at(text, m.start()))
        m = _GALONES_RE.search(text)
        if m:
            fields["galones"] = _field(_norm_amount(m.group(1)) if "," in m.group(1) or "." in m.group(1) else m.group(1), "high", _line_at(text, m.start()))
        else:
            m = _LITROS_RE.search(text)
            if m:
                fields["litros"] = _field(m.group(1), "high", _line_at(text, m.start()))

    needs_review = sorted(
        name for name, f in fields.items() if f["confidence"] != "high"
    )
    return {
        "extractor": EXTRACTOR_VERSION,
        "doc_type_suggested": _suggest_doc_type(text),
        "fields": fields,
        "needs_review": needs_review,
    }


def run_extraction(text: str, *, doc_type: str = "") -> dict[str, Any]:
    """Puerta única de la etapa F2. Hoy: extractor determinista. Cuando el merge train
    de diagnostics aterrice, un extractor LLM (estructurado, detrás del kill switch)
    podrá decorar este resultado — sin cambiar el contrato del payload."""
    return extract_fields(text, doc_type=doc_type)
