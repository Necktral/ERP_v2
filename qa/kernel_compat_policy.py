from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class KernelCompatPolicy:
    compat_apps: tuple[str, ...]
    whitelist_files: tuple[str, ...]
    enforcement_level: str
    retirement_deadline: str
    notes: tuple[str, ...]


KERNEL_COMPAT_APPS: tuple[str, ...] = ("accounting", "facturacion", "inventarios", "payments")

_SHIM_WHITELIST = tuple(f"backend/src/apps/modulos/{app}/__init__.py" for app in KERNEL_COMPAT_APPS)
_TEST_WHITELIST = ("backend/src/tests/test_kernel_namespace_compat.py",)

DEFAULT_POLICY = KernelCompatPolicy(
    compat_apps=KERNEL_COMPAT_APPS,
    whitelist_files=_SHIM_WHITELIST + _TEST_WHITELIST,
    enforcement_level="ratchet",
    retirement_deadline="2026-06-22",
    notes=(
        "No se permiten nuevos imports legacy apps.modulos.<kernel> fuera de la whitelist.",
        "Modo strict: el uso legacy debe llegar a cero.",
    ),
)


def allowed_references(*, enforcement_level: str | None = None) -> set[str]:
    mode = (enforcement_level or DEFAULT_POLICY.enforcement_level).strip().lower()
    if mode == "strict":
        return set()
    return set(DEFAULT_POLICY.whitelist_files)
