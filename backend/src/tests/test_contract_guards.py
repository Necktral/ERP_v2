"""
Guard tests anti-drift (estáticos, basados en AST del código fuente).

No ejercitan comportamiento en runtime: escanean el árbol de `apps/kernels` y
`apps/modulos` para detectar, en tiempo de test, dos clases de drift que hoy solo
fallan en producción por caminos sin cobertura:

1. AUDITORÍA: todo literal `event_type=` / `reason_code=` / `subject_type=` pasado a
   `write_event(...)` debe pertenecer a los allowlists de `audit/contracts.py`.
   (Habría atrapado el bug `NOMINA_OK` de la sesión anterior.)

2. RBAC: toda vista (subclase de APIView/ViewSet) debe declarar `permission_classes`
   o sobreescribir `get_permissions`, salvo bases abstractas explícitamente permitidas.
"""
from __future__ import annotations

import ast
import pathlib

from apps.modulos.audit.contracts import (
    ALLOWED_EVENT_TYPES,
    ALLOWED_REASON_CODES,
    ALLOWED_SUBJECT_TYPES,
)

# Raíz del paquete de apps (este archivo vive en backend/src/tests/)
_SRC = pathlib.Path(__file__).resolve().parent.parent  # .../backend/src
_ROOTS = [_SRC / "apps" / "kernels", _SRC / "apps" / "modulos"]

# Bases que identifican una vista DRF.
_VIEW_BASES = {
    "APIView", "ViewSet", "ModelViewSet", "GenericAPIView",
    "ListAPIView", "GenericViewSet", "ListCreateAPIView",
}

# Bases abstractas que NO sirven endpoints por sí mismas; sus subclases declaran permisos.
_ABSTRACT_VIEW_ALLOWLIST = {
    "ReportingAPIView",
}

# Keyword de write_event → allowlist correspondiente.
_AUDIT_KW_TO_ALLOWLIST = {
    "event_type": ALLOWED_EVENT_TYPES,
    "reason_code": ALLOWED_REASON_CODES,
    "subject_type": ALLOWED_SUBJECT_TYPES,
}


def _iter_py_files():
    for root in _ROOTS:
        for f in root.rglob("*.py"):
            if "__pycache__" in f.parts:
                continue
            # No auditamos los propios tests (usan literales de ejemplo a propósito).
            if "tests" in f.parts:
                continue
            yield f


def _iter_views_files():
    for root in _ROOTS:
        for f in root.rglob("views.py"):
            if "__pycache__" in f.parts:
                continue
            yield f


def _base_names(node: ast.ClassDef) -> list[str]:
    names = []
    for b in node.bases:
        if isinstance(b, ast.Name):
            names.append(b.id)
        elif isinstance(b, ast.Attribute):
            names.append(b.attr)
    return names


def _call_func_name(call: ast.Call) -> str:
    f = call.func
    if isinstance(f, ast.Name):
        return f.id
    if isinstance(f, ast.Attribute):
        return f.attr
    return ""


# ---------------------------------------------------------------------------
# 1. Guard de auditoría
# ---------------------------------------------------------------------------

def _collect_audit_violations():
    violations = []
    for f in _iter_py_files():
        try:
            tree = ast.parse(f.read_text(encoding="utf-8"), filename=str(f))
        except SyntaxError:
            continue
        for call in ast.walk(tree):
            if not isinstance(call, ast.Call):
                continue
            if _call_func_name(call) != "write_event":
                continue
            for kw in call.keywords:
                if kw.arg not in _AUDIT_KW_TO_ALLOWLIST:
                    continue
                # Solo verificamos literales string; valores dinámicos (variables) se omiten.
                if not (isinstance(kw.value, ast.Constant) and isinstance(kw.value.value, str)):
                    continue
                value = kw.value.value
                allow = _AUDIT_KW_TO_ALLOWLIST[kw.arg]
                # reason_code="" es válido (se ignora en validate_reason_code).
                if kw.arg == "reason_code" and value == "":
                    continue
                if value not in allow:
                    rel = f.relative_to(_SRC)
                    violations.append(f"{rel}:{kw.value.lineno} {kw.arg}={value!r} no está en el allowlist")
    return violations


def test_write_event_uses_only_allowlisted_audit_codes():
    violations = _collect_audit_violations()
    assert not violations, (
        "write_event usa códigos de auditoría fuera de contracts.py "
        "(agrégalos a ALLOWED_EVENT_TYPES/REASON_CODES/SUBJECT_TYPES):\n"
        + "\n".join(violations)
    )


def test_audit_guard_actually_scans_calls():
    """Sanity: el guard realmente encuentra llamadas write_event (evita falso verde)."""
    found = 0
    for f in _iter_py_files():
        try:
            tree = ast.parse(f.read_text(encoding="utf-8"), filename=str(f))
        except SyntaxError:
            continue
        for call in ast.walk(tree):
            if isinstance(call, ast.Call) and _call_func_name(call) == "write_event":
                found += 1
    assert found >= 20, f"Esperaba >=20 llamadas write_event en kernels/modulos, encontré {found}"


# ---------------------------------------------------------------------------
# 2. Guard de RBAC
# ---------------------------------------------------------------------------

def _collect_unprotected_views():
    unprotected = []
    total = 0
    for f in _iter_views_files():
        try:
            tree = ast.parse(f.read_text(encoding="utf-8"), filename=str(f))
        except SyntaxError:
            continue
        for node in ast.walk(tree):
            if not isinstance(node, ast.ClassDef):
                continue
            if not any(b in _VIEW_BASES for b in _base_names(node)):
                continue
            if node.name in _ABSTRACT_VIEW_ALLOWLIST:
                continue
            total += 1
            has_pc = any(
                isinstance(s, ast.Assign)
                and any(isinstance(t, ast.Name) and t.id == "permission_classes" for t in s.targets)
                for s in node.body
            )
            has_get_perm = any(
                isinstance(s, ast.FunctionDef) and s.name == "get_permissions"
                for s in node.body
            )
            if not (has_pc or has_get_perm):
                rel = f.relative_to(_SRC)
                unprotected.append(f"{rel}:{node.lineno}::{node.name}")
    return unprotected, total


def test_every_view_declares_permissions():
    unprotected, total = _collect_unprotected_views()
    assert total >= 100, f"Esperaba >=100 clases de vista, encontré {total} (¿roto el scanner?)"
    assert not unprotected, (
        "Vistas sin permission_classes ni get_permissions (heredarían el default global "
        "en silencio). Declara permisos o agrégalas a _ABSTRACT_VIEW_ALLOWLIST si son bases:\n"
        + "\n".join(unprotected)
    )
