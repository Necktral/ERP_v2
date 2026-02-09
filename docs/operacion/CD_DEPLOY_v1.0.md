# CD Deploy (VPS + Docker Compose)

Versión: v1.0  
Fecha: 2026-02-09  
Estado: Guia operativa

## Objetivo

Desplegar backend y web en VPS usando imagenes en GHCR y `compose.prod.yaml`.

## Requisitos

- VPS con Docker y Docker Compose v2.
- Repo clonado en el VPS (path fijo).
- Archivo `.env` en el VPS con variables de prod.

## Secrets requeridos (GitHub Actions)

- `VPS_HOST`: IP o hostname del VPS.
- `VPS_USER`: usuario SSH.
- `VPS_SSH_KEY`: llave privada para SSH.
- `VPS_PATH`: ruta del repo en el VPS (ej: `/opt/ERP_CRM`).
- `GHCR_USER`: usuario del registry (ej: `necktral`).
- `GHCR_TOKEN`: token con permiso `read:packages`.

## Como funciona

Workflow: `.github/workflows/cd.yml`.

1. Push a `master` o `main`.
2. CI construye y publica imagenes:
   - `ghcr.io/OWNER/necktral-backend:<sha>`
   - `ghcr.io/OWNER/necktral-web:<sha>`
3. CD hace SSH al VPS, actualiza el repo, hace `docker compose pull` y `up -d`.
4. El backend ejecuta migraciones y collectstatic en el entrypoint.

## Rollback rapido

En el VPS:

```bash
export IMAGE_TAG=<sha_anterior>
docker compose -f compose.prod.yaml pull
docker compose -f compose.prod.yaml up -d --remove-orphans
```

## Notas

- `compose.prod.yaml` usa `IMAGE_TAG` y `IMAGE_REGISTRY` como parametros.
- Si no hay `IMAGE_TAG`, se usa `latest`.
- El build/push usa el `GITHUB_TOKEN` del runner; el deploy usa `GHCR_TOKEN` en el VPS.
