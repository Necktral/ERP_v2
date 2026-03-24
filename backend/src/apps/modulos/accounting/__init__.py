"""Release N/N+1 compatibility shim.

Legacy namespace: apps.modulos.accounting
Canonical namespace: apps.kernels.accounting
"""

from importlib import import_module
import logging
import sys

_TARGET = "apps.kernels.accounting"
_SUBMODULES = (
    "apps",
    "models",
    "services",
    "serializers",
    "views",
    "urls",
    "phase7",
    "phase7b",
    "phase8",
    "staging_ops",
    "certification",
    "certification_phase7",
    "certification_phase7b",
    "certification_phase11",
    "certification_phase12",
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
