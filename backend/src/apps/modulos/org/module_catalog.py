"""Catálogo canónico de módulos del ERP (única fuente de verdad).

Tres semánticas de "módulo" conviven en el sistema y se componen:

* ``allowed_modules``  — derivado de permisos RBAC (¿el USUARIO puede tocarlo?).
* ``enabled_modules``  — habilitación por empresa (¿la EMPRESA lo ocupa?), persistida
  en ``org.CompanyModule`` y resuelta contra los defaults de este catálogo.
* ``effective_modules`` — la intersección ``allowed ∩ enabled`` (lo que el front muestra).

Este módulo define el catálogo y helpers de solo-lectura. No depende de Django:
es data + funciones puras, importable desde modelos, servicios, selectores y vistas
sin crear edges nuevos en el ratchet de arquitectura.

`code` está alineado con las claves que el front ya consume vía
``apps.modulos.accounts.views._MODULE_PERMISSION_PREFIXES`` (follow-up: derivar
ese mapa de este catálogo para eliminar la duplicación).
"""

from __future__ import annotations

from dataclasses import dataclass, field


class ModuleCategory:
    CORE = "CORE"
    OPERATIONS = "OPERATIONS"
    FINANCE = "FINANCE"
    VERTICAL = "VERTICAL"


@dataclass(frozen=True)
class ModuleSpec:
    """Especificación inmutable de un módulo del catálogo."""

    code: str
    label: str
    category: str
    #: Módulo de infraestructura siempre activo; no se puede deshabilitar.
    core: bool = False
    #: Estado por defecto cuando la empresa no tiene un override explícito.
    default_enabled: bool = False
    #: Prefijos de permiso que "encienden" el módulo en allowed_modules (DRY futuro).
    permission_prefixes: tuple[str, ...] = ()
    #: Campo correspondiente en OperationalPostingConfig (sync GL = follow-up).
    posting_key: str | None = None
    #: Códigos de módulo que este requiere para poder habilitarse.
    depends_on: tuple[str, ...] = field(default_factory=tuple)

    def __post_init__(self) -> None:
        # Invariante de catálogo: lo core es, por definición, siempre habilitado.
        if self.core and not self.default_enabled:
            raise ValueError(f"Módulo core '{self.code}' debe tener default_enabled=True")


# Orden estable = orden de presentación en el catálogo del front.
_SPECS: tuple[ModuleSpec, ...] = (
    # --- CORE (always-on, no desactivables) ---
    ModuleSpec("organization", "Organización", ModuleCategory.CORE, core=True, default_enabled=True, permission_prefixes=("org.",)),
    ModuleSpec("human_resources", "Recursos Humanos", ModuleCategory.CORE, core=True, default_enabled=True, permission_prefixes=("hr.",)),
    ModuleSpec("accounting", "Contabilidad", ModuleCategory.CORE, core=True, default_enabled=True, permission_prefixes=("accounting.",)),
    ModuleSpec("audit", "Auditoría", ModuleCategory.CORE, core=True, default_enabled=True, permission_prefixes=("audit.",)),
    ModuleSpec("synchronization", "Sincronización", ModuleCategory.CORE, core=True, default_enabled=True, permission_prefixes=("sync.",)),
    # --- OPERATIONS (set base ON por defecto) ---
    ModuleSpec("payroll", "Nómina", ModuleCategory.OPERATIONS, default_enabled=True, permission_prefixes=("nomina.",), posting_key="enable_nomina"),
    ModuleSpec("billing", "Facturación", ModuleCategory.OPERATIONS, default_enabled=True, permission_prefixes=("billing.",), posting_key="enable_billing"),
    ModuleSpec("reporting", "Reportes", ModuleCategory.OPERATIONS, default_enabled=True, permission_prefixes=("report.",)),
    ModuleSpec("analytics", "Analítica / Dashboard", ModuleCategory.OPERATIONS, default_enabled=True, permission_prefixes=("report.dashboard.",)),
    # --- FINANCE / VERTICALES (OFF hasta activar) ---
    ModuleSpec("inventory", "Inventario", ModuleCategory.VERTICAL, default_enabled=False, permission_prefixes=("inventory.",), posting_key="enable_inventory"),
    ModuleSpec("procurement", "Compras", ModuleCategory.VERTICAL, default_enabled=False, permission_prefixes=("procurement.",)),
    ModuleSpec("portfolio", "Cartera (CxC / CxP)", ModuleCategory.FINANCE, default_enabled=False, permission_prefixes=("portfolio.",)),
    ModuleSpec("payments", "Pagos / Caja", ModuleCategory.FINANCE, default_enabled=False, permission_prefixes=("payments.", "payment.")),
    ModuleSpec("retail_pos", "Punto de Venta", ModuleCategory.VERTICAL, default_enabled=False, permission_prefixes=("retail.pos.",)),
    ModuleSpec("fuel", "Estación de Servicio", ModuleCategory.VERTICAL, default_enabled=False, permission_prefixes=("fuel.",)),
    ModuleSpec("cec", "CEC", ModuleCategory.VERTICAL, default_enabled=False, permission_prefixes=("cec.",)),
)

_BY_CODE: dict[str, ModuleSpec] = {spec.code: spec for spec in _SPECS}


def get_catalog() -> tuple[ModuleSpec, ...]:
    """Catálogo completo en orden de presentación."""
    return _SPECS


def get_spec(code: str) -> ModuleSpec | None:
    """Spec de un módulo, o ``None`` si el código no existe en el catálogo."""
    return _BY_CODE.get(code)


def is_known(code: str) -> bool:
    """¿``code`` pertenece al catálogo?"""
    return code in _BY_CODE


def all_codes() -> tuple[str, ...]:
    return tuple(_BY_CODE.keys())


def core_codes() -> frozenset[str]:
    """Códigos de módulos core (siempre habilitados, no togglables)."""
    return frozenset(spec.code for spec in _SPECS if spec.core)


def default_state() -> dict[str, bool]:
    """Estado por defecto del catálogo (sin overrides de empresa)."""
    return {spec.code: spec.default_enabled for spec in _SPECS}
