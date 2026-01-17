#!/usr/bin/env bash
set -euo pipefail

cd /app/login_module

: "${DJANGO_SETTINGS_MODULE:=config.settings.dev}"
: "${DB_HOST:=db}"
: "${DB_PORT:=5432}"

export DJANGO_SETTINGS_MODULE

# Esperar a Postgres
python - <<'PY'
import os, time, socket
host = os.getenv('DB_HOST', 'db')
port = int(os.getenv('DB_PORT', '5432'))

deadline = time.time() + 60
last_err = None
while time.time() < deadline:
    try:
        with socket.create_connection((host, port), timeout=2):
            print('db_ready')
            raise SystemExit(0)
    except OSError as e:
        last_err = e
        time.sleep(2)

print(f'db_not_ready: {last_err}')
raise SystemExit(1)
PY

python src/manage.py migrate --noinput

exec python src/manage.py runserver 0.0.0.0:8000
