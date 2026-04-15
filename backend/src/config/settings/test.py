from .base import *  # noqa

import hashlib
import os
import re

from rest_framework.settings import api_settings

# Tests: deterministas y rápidos
DEBUG = False
SECRET_KEY = "test-signing-key-with-minimum-32-bytes-2026"
SIMPLE_JWT = {
    **SIMPLE_JWT,
    "SIGNING_KEY": SECRET_KEY,
}

# Tests: mantener header para facilitar clientes no-browser
AUTH_TOKEN_TRANSPORT = "header"
# Tests: no exigir HTTPS por defecto en cookie transport salvo override explícito por caso.
AUTH_COOKIE_REQUIRE_HTTPS = False

# Tests: permitir host por defecto de APIClient
ALLOWED_HOSTS = list(ALLOWED_HOSTS) + ["testserver"]

PASSWORD_HASHERS = [
    "django.contrib.auth.hashers.MD5PasswordHasher",
]

# Tests: desactivar Axes para evitar lockouts en flujos masivos
AXES_ENABLED = False

MIDDLEWARE = [m for m in MIDDLEWARE if m != "axes.middleware.AxesMiddleware"]

AUTHENTICATION_BACKENDS = [
    "django.contrib.auth.backends.ModelBackend",
]

# Tests: relajar validadores de password para evitar friccion
AUTH_PASSWORD_VALIDATORS = []

# Throttling activo pero con límites altos para evitar 429 en tests
REST_FRAMEWORK = {
    **REST_FRAMEWORK,
    "DEFAULT_THROTTLE_RATES": {
        "anon": "10000/min",
        "user": "10000/min",
        "auth_login": "10000/min",
        "auth_refresh": "10000/min",
        "auth_logout": "10000/min",
        "auth_sensitive": "10000/min",
        "me_read": "10000/min",
        "me_acl_read": "10000/min",
        "context_read": "10000/min",
        "sync_batch": "10000/min",
        "admin_writes": "10000/min",
        "heavy_reads": "10000/min",
    },
}


def _normalize_token(value: str) -> str:
    token = re.sub(r"[^a-zA-Z0-9_]+", "_", str(value or "").strip()).strip("_").lower()
    if not token:
        return "default"
    if len(token) <= 24:
        return token
    digest = hashlib.sha1(token.encode("utf-8")).hexdigest()[:8]
    return f"{token[:15]}_{digest}"


def _build_pytest_test_db_name() -> str:
    base_name = _normalize_token(os.getenv("PYTEST_DB_BASE_NAME", "test_erp_db"))
    slot = str(os.getenv("PYTEST_DB_SLOT", "")).strip()
    worker = str(os.getenv("PYTEST_XDIST_WORKER", "")).strip()

    if slot:
        suffix = f"slot_{_normalize_token(slot)}"
    elif worker:
        suffix = f"worker_{_normalize_token(worker)}"
    else:
        suffix = f"pid_{os.getpid()}"

    # PostgreSQL limita identificadores de base de datos a 63 caracteres.
    return f"{base_name}_{suffix}"[:63]


DATABASES = {
    **DATABASES,
    "default": {
        **DATABASES["default"],
        "TEST": {
            **DATABASES["default"].get("TEST", {}),
            "NAME": _build_pytest_test_db_name(),
        },
    },
}


api_settings.reload()
