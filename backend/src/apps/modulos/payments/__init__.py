"""Release N/N+1 compatibility shim.

Legacy namespace: apps.modulos.payments
Canonical namespace: apps.kernels.payments
"""

from importlib import import_module
import logging
import sys

_TARGET = "apps.kernels.payments"
_SUBMODULES = (
    "apps",
    "models",
    "services",
    "serializers",
    "views",
    "urls",
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
