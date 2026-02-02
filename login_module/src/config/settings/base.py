# RBAC (modo transición): incluye roles globales legacy (UserRole) además de RoleAssignment scoped
RBAC_INCLUDE_GLOBAL_USERROLES = True
AXES_RESET_ON_SUCCESS = True
"""
NOTA:
- REST_FRAMEWORK se define UNA sola vez más abajo para evitar shadowing.
- AXES_* se define UNA sola vez en base (prod-safe) y se sobreescribe en dev.py.
"""


# (AXES_* se define abajo en formato correcto con timedelta)

from datetime import timedelta
from pathlib import Path
import sys

import environ

# base.py está en: backend/src/config/settings/base.py
# BASE_DIR = backend/src
BASE_DIR = Path(__file__).resolve().parents[2]  # -> backend/src
ENV_FILE = BASE_DIR.parent.parent / ".env"  # -> ERP_CRM/.env

# Permite importar paquetes ubicados en la raíz del repo (por ejemplo: modulos.*)
REPO_ROOT = BASE_DIR.parent.parent  # -> ERP_CRM/
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

env = environ.Env(
    DJANGO_DEBUG=(bool, False),
    DJANGO_SECRET_KEY=(str, "unsafe-dev-secret"),
    DJANGO_ALLOWED_HOSTS=(list, ["localhost", "127.0.0.1"]),
    DJANGO_CORS_ALLOWED_ORIGINS=(list, ["http://localhost:3000"]),
    DJANGO_CSRF_TRUSTED_ORIGINS=(list, ["http://localhost:3000"]),
)

if ENV_FILE.exists():
    env.read_env(str(ENV_FILE))

SECRET_KEY = env("DJANGO_SECRET_KEY")
DEBUG = env("DJANGO_DEBUG")
ALLOWED_HOSTS = env("DJANGO_ALLOWED_HOSTS")

# --- Logging (request_id obligatorio) ---

LOGGING = {
    "version": 1,
    "disable_existing_loggers": False,
    "filters": {
        "request_id": {"()": "config.logging_utils.RequestIdFilter"},
    },
    "formatters": {
        "verbose": {
            "format": "[{levelname}] {asctime} {name}: {message} (request_id={request_id})",
            "style": "{",
        },
        "json": {"()": "config.logging_utils.JsonFormatter"},
    },
    "handlers": {
        "console": {
            "class": "logging.StreamHandler",
            "filters": ["request_id"],
            "formatter": "json" if not DEBUG else "verbose",
        },
    },
    "root": {
        "handlers": ["console"],
        "level": "INFO",
    },
    "loggers": {
        "apps.audit": {
            "handlers": ["console"],
            "level": "DEBUG",
            "propagate": False,
        },
        "apps.accounts": {
            "handlers": ["console"],
            "level": "DEBUG",
            "propagate": False,
        },
    },
}

# CORS / CSRF para PWA
CORS_ALLOWED_ORIGINS = env("DJANGO_CORS_ALLOWED_ORIGINS")
CSRF_TRUSTED_ORIGINS = env("DJANGO_CSRF_TRUSTED_ORIGINS")

from corsheaders.defaults import default_headers

CORS_ALLOW_HEADERS = list(default_headers) + [
    "x-company-id",
    "x-branch-id",
    "x-data-company-id",
    "x-data-branch-id",
    "x-device-id",
    "x-device-ts",
    "x-device-nonce",
    "x-device-signature",
    "x-request-id",
]

# Permite que el frontend lea el request id devuelto por el backend
CORS_EXPOSE_HEADERS = [
    "X-Request-Id",
]

AUDIT_HMAC_KEY = env("AUDIT_HMAC_KEY")
# Nombre contractual del módulo que emite eventos de auditoría para este servicio.
AUDIT_MODULE_NAME = "AUTH"
AUDIT_SCHEMA_VERSION = 1

TIME_ZONE = "America/Managua"
USE_TZ = True

LANGUAGE_CODE = "es"

INSTALLED_APPS = [
    # Django
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
    # Terceros
    "rest_framework",
    "rest_framework_simplejwt",
    "rest_framework_simplejwt.token_blacklist",
    "corsheaders",
    "drf_spectacular",
    "drf_spectacular_sidecar",
    "django_filters",
    "axes",
    "csp",
    # Apps del proyecto
    "apps.common",
    "apps.audit",
    "apps.rbac",
    "apps.accounts.apps.AccountsConfig",
    "apps.iam.apps.IamConfig",
    "apps.org.apps.OrgConfig",  # <-- NUEVO
    "apps.hr.apps.HrConfig",  # <-- NUEVO
    "apps.sync_engine",
    "apps.sync.apps.SyncConfig",
    # Módulos de dominio (raíz/modulos)
    # (Se agregan abajo con el patrón INSTALLED_APPS += [...])
]

INSTALLED_APPS += [
    "modulos.estacion_servicios",
    "modulos.inventarios",
    "modulos.facturacion",
]

MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    "config.middleware.request_id.RequestIdMiddleware",
    # CORS lo más arriba posible (antes de CommonMiddleware y WhiteNoise)
    "corsheaders.middleware.CorsMiddleware",
    # WhiteNoise sirve estáticos (útil incluso en dev si lo deseas)
    "whitenoise.middleware.WhiteNoiseMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
    # Axes al final (recomendación oficial)
    "axes.middleware.AxesMiddleware",
    "apps.audit.middleware.AuditAccessDeniedMiddleware",
    "config.middleware.api_error_envelope.ApiErrorEnvelopeMiddleware",
]

ROOT_URLCONF = "config.urls"

TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        "DIRS": [],
        "APP_DIRS": True,
        "OPTIONS": {
            "context_processors": [
                "django.template.context_processors.debug",
                "django.template.context_processors.request",
                "django.contrib.auth.context_processors.auth",
                "django.contrib.messages.context_processors.messages",
            ],
        },
    },
]

WSGI_APPLICATION = "config.wsgi.application"


# Configuración para PostgreSQL usando variables de entorno
DATABASES = {
    "default": {
        "ENGINE": env("DB_ENGINE", default="django.db.backends.postgresql"),
        "NAME": env("POSTGRES_DB", default=env("DB_NAME", default="loggin_db")),
        "USER": env("POSTGRES_USER", default=env("DB_USER", default="loggin_user")),
        "PASSWORD": env(
            "POSTGRES_PASSWORD",
            default=env("DB_PASSWORD", default=""),
        ),
        "HOST": env("POSTGRES_HOST", default=env("DB_HOST", default="127.0.0.1")),
        "PORT": env("POSTGRES_PORT", default=env("DB_PORT", default="5432")),
        "CONN_MAX_AGE": 60,
    }
}

AUTH_USER_MODEL = "accounts.User"

# Axes: backend primero (recomendación oficial)
AUTHENTICATION_BACKENDS = [
    "axes.backends.AxesStandaloneBackend",
    "django.contrib.auth.backends.ModelBackend",
]

# Password hashing fuerte
PASSWORD_HASHERS = [
    "django.contrib.auth.hashers.Argon2PasswordHasher",
    "django.contrib.auth.hashers.PBKDF2PasswordHasher",
    "django.contrib.auth.hashers.PBKDF2SHA1PasswordHasher",
    "django.contrib.auth.hashers.BCryptSHA256PasswordHasher",
]

AUTH_PASSWORD_VALIDATORS = [
    {"NAME": "django.contrib.auth.password_validation.UserAttributeSimilarityValidator"},
    {"NAME": "django.contrib.auth.password_validation.MinimumLengthValidator"},
    {"NAME": "django.contrib.auth.password_validation.CommonPasswordValidator"},
    {"NAME": "django.contrib.auth.password_validation.NumericPasswordValidator"},
]


# Configuración robusta de archivos estáticos
STATIC_URL = "/static/"
STATIC_ROOT = str(BASE_DIR.parent / "staticfiles")
# Permite incluir directorios adicionales de estáticos en desarrollo
STATICFILES_DIRS = [
    str(BASE_DIR / "static"),
]
# WhiteNoise: storage comprimido y con manifest para producción
STORAGES = {
    "staticfiles": {"BACKEND": "whitenoise.storage.CompressedManifestStaticFilesStorage"},
}

# Crear el directorio STATIC_ROOT si no existe (robustez en dev)
import os

os.makedirs(STATIC_ROOT, exist_ok=True)

DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"

# DRF
REST_FRAMEWORK = {
    "EXCEPTION_HANDLER": "config.drf_exception_handler.custom_exception_handler",
    "DEFAULT_AUTHENTICATION_CLASSES": ("apps.iam.authentication.JWTAuthWithOrgContext",),
    "DEFAULT_PERMISSION_CLASSES": ("rest_framework.permissions.IsAuthenticated",),
    "DEFAULT_SCHEMA_CLASS": "drf_spectacular.openapi.AutoSchema",
    "DEFAULT_FILTER_BACKENDS": ("django_filters.rest_framework.DjangoFilterBackend",),
    "DEFAULT_THROTTLE_CLASSES": (
        "rest_framework.throttling.AnonRateThrottle",
        "rest_framework.throttling.UserRateThrottle",
        "rest_framework.throttling.ScopedRateThrottle",
        "config.throttling.DeviceScopedRateThrottle",
    ),
    "DEFAULT_THROTTLE_RATES": {
        "anon": "60/min",
        "user": "600/min",
        "auth_login": "20/min",
        "auth_sensitive": "10/min",
        "sync_batch": "30/min",
        "admin_writes": "60/min",
        "heavy_reads": "60/min",
    },
}

# SimpleJWT
SIMPLE_JWT = {
    "ACCESS_TOKEN_LIFETIME": timedelta(minutes=10),
    "REFRESH_TOKEN_LIFETIME": timedelta(days=7),
    "ROTATE_REFRESH_TOKENS": True,
    "BLACKLIST_AFTER_ROTATION": True,
    "UPDATE_LAST_LOGIN": True,
}

# CORS / CSRF para PWA
CORS_ALLOWED_ORIGINS = env("DJANGO_CORS_ALLOWED_ORIGINS")
CSRF_TRUSTED_ORIGINS = env("DJANGO_CSRF_TRUSTED_ORIGINS")

# drf-spectacular + sidecar (UI embebida)
SPECTACULAR_SETTINGS = {
    "TITLE": "Login Module API",
    "DESCRIPTION": "Auth + RBAC + Audit",
    "VERSION": "0.1.0",
    "SERVE_INCLUDE_SCHEMA": False,
    "SWAGGER_UI_DIST": "SIDECAR",
    "SWAGGER_UI_FAVICON_HREF": "SIDECAR",
    "REDOC_DIST": "SIDECAR",
}

# Axes (política inicial)
AXES_FAILURE_LIMIT = 5
AXES_COOLOFF_TIME = timedelta(minutes=15)
AXES_LOCKOUT_PARAMETERS = ["ip_address", ["username", "user_agent"]]


# CSP nueva sintaxis para django-csp >= 4.0
CONTENT_SECURITY_POLICY = {
    "DIRECTIVES": {
        "default-src": ("'self'",),
        "script-src": ("'self'",),
        "style-src": ("'self'",),
    }
}
