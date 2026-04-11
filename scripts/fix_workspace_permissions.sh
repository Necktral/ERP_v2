#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
HOST_UID="${HOST_UID:-$(id -u)}"
HOST_GID="${HOST_GID:-$(id -g)}"

TARGETS=(
  ".ruff_cache"
  "backend/.mypy_cache"
  "frontend/node_modules"
  "frontend/dist"
  "qa/reports"
)

for rel in "${TARGETS[@]}"; do
  mkdir -p "${ROOT_DIR}/${rel}"
done

if ! command -v docker >/dev/null 2>&1; then
  echo "[perm] docker no está disponible; no se puede corregir ownership de artefactos creados por contenedor."
  exit 0
fi

echo "[perm] Ajustando ownership a ${HOST_UID}:${HOST_GID} en rutas de artefactos..."
docker run --rm \
  -v "${ROOT_DIR}:/workspace" \
  alpine:3.20 \
  sh -lc "chown -R ${HOST_UID}:${HOST_GID} \
    /workspace/.ruff_cache \
    /workspace/backend/.mypy_cache \
    /workspace/frontend/node_modules \
    /workspace/frontend/dist \
    /workspace/qa/reports"

echo "[perm] Ownership corregido."
