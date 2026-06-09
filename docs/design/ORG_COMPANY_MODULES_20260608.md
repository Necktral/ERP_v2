# Org Company Modules

## Control

Documento: `ORG_COMPANY_MODULES_20260608.md`
Fecha: 2026-06-08
Estado: Design note para guard de blast radius
Corte: `feat/org-company-modules`

## Decision

ORG mantiene el registro operacional de módulos habilitados por compañía mediante `CompanyModule`. RBAC sigue siendo el dueño de permisos y acciones; el registro de módulos solo define si una compañía ocupa un módulo. Las capacidades que consume el cliente se separan en tres listas:

- `allowed_modules`: derivado de permisos RBAC del usuario.
- `enabled_modules`: derivado de `CompanyModule` y defaults del catálogo.
- `effective_modules`: intersección entre permisos y módulos habilitados.

Las rutas canónicas post-API-versioning viven bajo `/api/v1/org/modules/`. La ruta legacy `/api/org/modules/` se conserva mientras el router legacy siga montado.

## Scope

Incluido:

- Catálogo canónico de módulos.
- Modelo `CompanyModule` y migración `org.0006`.
- Endpoint GET/PUT de módulos por compañía.
- Auditoría `ORG_MODULES_UPDATED`.
- `require_module(code)` como enforcement complementario a RBAC.
- Exposición de `enabled_modules` y `effective_modules` en sesión/ACL.
- Lectura desde Accounting para resolver `enable_billing`, `enable_inventory` y `enable_nomina`.

Fuera de alcance:

- Dependabot.
- Frontend funcional.
- Sync HMAC.
- Funcionalidad de nómina y `PayrollEntry`.
- Payments, Portfolio, CEC y Shadow Ledger histórico.
- Escritura de configuración ORG desde Accounting.

## Riesgos Residuales

- `allowed_modules` permanece como contrato legacy de navegación hasta que el cliente consuma solo `effective_modules`.
- La habilitación de módulos no reemplaza permisos RBAC; endpoints deben mantener ambos controles cuando aplique.
- Accounting debe tratar `CompanyModule` como señal de lectura y no como fuente para reescribir históricos.

## QA Gates

Este corte requiere `manage.py check`, `makemigrations --check`, ruff focal de ORG/RBAC/Audit/Accounting, tests de `/api/v1/org/modules/`, compatibilidad legacy `/api/org/modules/`, `qa-route-contract-guard`, `qa-migration-safety-guard`, `qa-architecture-dependency-guard`, `qa-coverage-by-domain-guard` y perfil QA de PR completo.
