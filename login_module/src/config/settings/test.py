from .base import *  # noqa

from rest_framework.settings import api_settings

# Tests: deterministas y rápidos
DEBUG = False

PASSWORD_HASHERS = [
    "django.contrib.auth.hashers.MD5PasswordHasher",
]

# Tests: desactivar Axes + throttling para evitar 429 en flujos de login masivos
AXES_ENABLED = False

MIDDLEWARE = [m for m in MIDDLEWARE if m != "axes.middleware.AxesMiddleware"]

AUTHENTICATION_BACKENDS = [
    "django.contrib.auth.backends.ModelBackend",
]

REST_FRAMEWORK = {
    **REST_FRAMEWORK,
    "DEFAULT_THROTTLE_CLASSES": (),
    "DEFAULT_THROTTLE_RATES": {},
}

api_settings.DEFAULTS["DEFAULT_THROTTLE_CLASSES"] = ()
api_settings.DEFAULTS["DEFAULT_THROTTLE_RATES"] = {}
api_settings.reload()
