"""Release N/N+1 compatibility shim.

Legacy namespace: apps.modulos.facturacion
Canonical namespace: apps.kernels.facturacion
"""

from importlib import import_module
import logging
import sys

_TARGET = "apps.kernels.facturacion"
_SUBMODULES = (
    "apps",
    "models",
    "services",
    "serializers",
    "views",
    "urls",
    "urls_legacy",
    "fiscal_adapters",
    "certification",
    "certification_phase9",
    "management",
    "management.commands",
    "migrations",
)

logging.getLogger("apps.compat").warning(
    "Deprecated namespace import in use: %s -> %s", __name__, _TARGET
)

for _submodule in _SUBMODULES:
    _old = f"{__name__}.{_submodule}"
    _new = f"{_TARGET}.{_submodule}"
    try:
        sys.modules.setdefault(_old, import_module(_new))
    except ModuleNotFoundError:
        continue
