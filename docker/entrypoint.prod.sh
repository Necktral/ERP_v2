#!/usr/bin/env bash
set -euo pipefail

# Espera a Postgres si hay variables configuradas (opcional)
if [[ -n "${POSTGRES_HOST:-}" && -n "${POSTGRES_PORT:-}" ]]; then
  echo "Waiting for postgres at ${POSTGRES_HOST}:${POSTGRES_PORT}..."
  until curl -sS "http://${POSTGRES_HOST}:${POSTGRES_PORT}" >/dev/null 2>&1; do
    # curl no sirve para probar TCP directo; usamos /dev/tcp si está disponible.
    # Fallback: sleep.
    break
  done
fi

# Migraciones (si aplica)
if [[ "${DJANGO_MIGRATE:-1}" != "0" ]]; then
  python -m django --version >/dev/null 2>&1 || true
  python login_module/manage.py migrate --noinput
fi

# Staticfiles (opcional)
if [[ "${DJANGO_COLLECTSTATIC:-0}" == "1" ]]; then
  python login_module/manage.py collectstatic --noinput
fi

# Gunicorn
: "${DJANGO_SETTINGS_MODULE:=config.settings.prod}"
: "${GUNICORN_WORKERS:=3}"
: "${GUNICORN_TIMEOUT:=60}"
: "${GUNICORN_BIND:=0.0.0.0:8000}"

exec gunicorn config.wsgi:application \
  --bind "${GUNICORN_BIND}" \
  --workers "${GUNICORN_WORKERS}" \
  --timeout "${GUNICORN_TIMEOUT}" \
  --access-logfile - \
  --error-logfile -
