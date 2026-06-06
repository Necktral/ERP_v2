# Platform API RBAC Sync CI Hardening

## Control

Documento: `PLATFORM_API_RBAC_SYNC_CI_HARDENING_PR15_20260608.md`
Fecha: 2026-06-08
Estado: Design note para guard de blast radius
Corte: PR15 - versionado API, retiro HMAC legacy y hardening RBAC/sync

## Decision

El corte mantiene `/api/v1/` como superficie canonica para rutas nuevas y conserva rutas legacy solo cuando tienen contrato de compatibilidad activo. El endpoint legacy HMAC queda retirado del API versionado y Sync V2 permanece expuesto mediante el motor `sync_engine`.

RBAC materializa asignaciones globales hacia scopes explicitos para reducir ambiguedad de permisos sin cambiar las reglas de negocio de dominios no relacionados. La configuracion de CI y los contratos QA se ajustan para que la validacion de rutas, seguridad y blast radius sea reproducible sobre el nuevo baseline de master.

## Scope

Incluido:

- Montaje canonico `/api/v1/` para API publica versionada.
- Compatibilidad de rutas nuevas de nomina y asistencia de campo bajo `/api/v1/nomina/`.
- Validacion de Sync V2 bajo `/api/v1/sync/`.
- Retiro del endpoint HMAC legacy dentro del API versionado.
- Migracion metadata-only para materializar `UserRole` global hacia asignaciones RBAC scoped.
- Actualizacion de contratos QA y evidencias de ruta/migracion relacionadas.

Fuera de alcance:

- Dependabot.
- Nuevos modulos de organizacion o company modules.
- Cambios funcionales en nomina fuera de compatibilidad de rutas.
- Frontend, app movil y cambios de producto no relacionados.
- Cambios en Payments, Portfolio, Accounting, CEC o sync HMAC fuera del retiro legacy declarado.

## Riesgos Residuales

- Clientes que intenten usar el endpoint HMAC legacy dentro de `/api/v1/` deben migrar a Sync V2.
- El corte toca varias capas de plataforma y por eso requiere revision por riesgo extremo.
- La compatibilidad depende de mantener tests de rutas canonicas y legacy sincronizados con `route_contract_guard`.

## QA Gates

Este corte requiere `manage.py check`, `makemigrations --check`, ruff, mypy, pruebas de rutas API v1, pruebas Sync V2, pruebas RBAC, `qa-migration-safety-guard`, `qa-route-contract-guard`, `qa-pr-blast-radius-guard` y perfil QA de PR completo antes de merge.
