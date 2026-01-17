#!/usr/bin/env bash
set -euo pipefail

cd /app/login_module

: "${DJANGO_SETTINGS_MODULE:=config.settings.dev}"

# Compat: permite usar POSTGRES_HOST/PORT o DB_HOST/PORT
: "${POSTGRES_HOST:=${DB_HOST:-db}}"
: "${POSTGRES_PORT:=${DB_PORT:-5432}}"

export DJANGO_SETTINGS_MODULE

# Espera simple a Postgres (sin herramientas extra)
echo "Waiting for postgres at ${POSTGRES_HOST}:${POSTGRES_PORT}..."
python - <<'PY'
import os, time, socket

host = os.getenv("POSTGRES_HOST", "db")
port = int(os.getenv("POSTGRES_PORT", "5432"))

deadline = time.time() + 60
while time.time() < deadline:
    try:
        with socket.create_connection((host, port), timeout=2):
            print("Postgres is up.")
            raise SystemExit(0)
    except OSError:
        time.sleep(1)

print("Postgres not reachable within 60s.")
raise SystemExit(1)
PY

# Migraciones automáticas en dev
python src/manage.py migrate --noinput

# Arranque servidor dev
exec python src/manage.py runserver 0.0.0.0:8000
