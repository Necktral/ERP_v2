# HANDOFF - Slice 3 ShellMode + Limpieza de Stores (2026-04-14)

Version: v1.0  
Fecha: 2026-04-14  
Tipo de cambio: `cross_domain`  
Modo de ejecucion: auto edit

## Diagnóstico del área

Estado inicial sobre `a00350fc`:

1. `bootstrap/session` ya estaba operativo y consumido por guard privado.
2. Persistia resolucion paralela en login/2FA (`acl.loadAcl()` fuera del carril canonico de bootstrap).
3. La separacion `Workbench/Taskflow` existia, pero el menu seguia mayormente basado solo en ACL y no en `allowed_modules`.
4. Faltaba explicitar y probar completamente la regla server-side de `shell_mode`.

## Alcance exacto

Incluido:

1. Endurecer pruebas backend de bootstrap para regla `X-Device-Class -> UA -> desktop`.
2. Consolidar frontend para que login/2FA y cambio de contexto usen bootstrap como fuente canonica.
3. Aplicar gating de menu por interseccion `allowed_modules + ACL`.
4. Documentar matriz canonica `modulo -> permiso minimo -> shell`.

Excluido:

1. UX final de inventarios/facturacion/estacion/dashboard.
2. Cambios en carril publico de enroll.
3. Cambios de contrato HTTP breaking.
4. Cierre del gate operativo manual movil 7/7 (permanece condicionado).

## Contratos impactados

1. Sin cambios breaking en contratos publicos.
2. Se mantiene endpoint canonico: `GET /api/auth/bootstrap/session/`.
3. Se preserva compatibilidad temporal de `/api/auth/me/` y `/api/auth/me/acl/` fuera del flujo canonico privado.
4. Se preserva carril publico: `/device/enroll`, `/api/sync/enroll/`, `/api/sync/batch/`.

## Pruebas / validación

Validaciones objetivo del slice:

1. Backend bootstrap:
   - `401` sin sesion.
   - `200` con shape canonico.
   - `shell_mode` determinista para header valido, header invalido + UA, y fallback desktop.
2. Frontend:
   - login/2FA con bootstrap forzado.
   - select-context refresca bootstrap.
   - menu privado gobernado por `allowed_modules + ACL`.
3. Guardias:
   - `qa-codex-governance-guard`
   - `qa-architecture-dependency-guard`
   - `qa-route-contract-guard`
   - `qa-readme-section-guard`
   - `qa-pr-blast-radius-guard`
   - `qa-backend-ruff`
   - `qa-backend-mypy`
   - `npm --prefix frontend run typecheck`

## Riesgos remanentes

1. Gate operativo externo pendiente: certificacion manual movil HTTPS 7/7.
2. Riesgo medio de drift funcional si nuevos modulos se publican sin actualizar matriz canonica shell/permisos.
3. Riesgo bajo de deuda si endpoints legacy (`me`, `me/acl`) se usan en flujos privados nuevos.

Mitigacion:

1. Mantener bootstrap como unica fuente para decisiones privadas.
2. Forzar actualizacion de matriz y gating en cada slice de modulo.
3. Restringir uso de endpoints legacy a compatibilidad no critica.

## Blast radius

1. Backend auth (`accounts/views.py`) y pruebas de bootstrap.
2. Frontend stores/pages/layout del carril privado (`Login`, `2FA`, `SelectContext`, `MainLayout`).
3. Documentacion de arquitectura SPA para matriz canonica de modulos/shell.

No impactado:

1. Dominios transaccionales de inventarios/facturacion/estacion.
2. Contrato de reporting/analytics.
3. Flujo publico de enroll.
