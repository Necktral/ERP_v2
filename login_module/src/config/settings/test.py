from .base import *  # noqa

from rest_framework.settings import api_settings

# Tests: deterministas y rápidos
DEBUG = False

PASSWORD_HASHERS = [
    "django.contrib.auth.hashers.MD5PasswordHasher",
]

# Tests: desactivar Axes para evitar lockouts en flujos masivos
AXES_ENABLED = False

MIDDLEWARE = [m for m in MIDDLEWARE if m != "axes.middleware.AxesMiddleware"]

AUTHENTICATION_BACKENDS = [
    "django.contrib.auth.backends.ModelBackend",
]

# Throttling activo pero con límites altos para evitar 429 en tests
REST_FRAMEWORK = {
    **REST_FRAMEWORK,
    "DEFAULT_THROTTLE_RATES": {
        "anon": "10000/min",
        "user": "10000/min",
        "auth_login": "10000/min",
        "auth_sensitive": "10000/min",
        "me_read": "10000/min",
        "me_acl_read": "10000/min",
        "context_read": "10000/min",
        "sync_batch": "10000/min",
        "admin_writes": "10000/min",
        "heavy_reads": "10000/min",
    },
}

api_settings.reload()
