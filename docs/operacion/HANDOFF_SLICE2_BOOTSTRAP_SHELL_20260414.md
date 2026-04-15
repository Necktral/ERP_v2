# HANDOFF - Slice 2 Bootstrap Unificado + Base de Shells (2026-04-14)

Version: v1.0  
Fecha: 2026-04-14  
Tipo de cambio: `cross_domain`  
Modo de ejecucion: auto edit

## Diagnóstico del área

Se partió de un estado parcial en `master` con:

1. Endpoint backend `/api/auth/bootstrap/session/` creado pero sin integración completa en frontend.
2. Store `session-bootstrap` existente, pero sin acople total con `router` y `auth.store`.
3. `MainLayout` sin separación funcional mínima Workbench/Taskflow.
4. Guardias privadas aún dependían de resolución paralela (`ensureSession`, `me`, `acl`) en lugar de bootstrap único.

Resultado del diagnóstico:

- El núcleo técnico del Slice 2 estaba incompleto.
- El mayor riesgo era estado inconsistente de sesión/contexto al no limpiar bootstrap en logout.

## Alcance exacto

Incluido:

1. Completar integración frontend para usar bootstrap como fuente canónica en rutas privadas.
2. Incorporar limpieza de estado bootstrap en cierre de sesión.
3. Introducir base de separación de shell en `MainLayout` (`Workbench` vs `Taskflow`) sin tocar UX final de módulos.
4. Mantener rutas existentes (no-breaking).
5. Validar con typecheck frontend y pruebas backend focalizadas.

Excluido:

1. Implementación final de pantallas de inventarios/facturación/estación/dashboard.
2. Cambios funcionales al carril público de enroll.
3. Cambios de contrato en reporting/analytics.
4. Certificación manual móvil 7/7 en dispositivo físico (sigue como gate operativo externo al código).

## Contratos impactados

1. Nuevo contrato aditivo backend ya integrado en frontend:
   - `GET /api/auth/bootstrap/session/`
2. Compatibilidad preservada:
   - `/api/auth/me/`
   - `/api/auth/me/acl/`
3. Sin cambios en contratos públicos de:
   - `/device/enroll`
   - `/api/sync/enroll/`
   - `/api/sync/batch/`
   - `/api/reporting/*`
   - `/analytics` (prefijo/política vigente)

## Pruebas / validación

Ejecuciones de esta iteración:

1. `npm --prefix frontend run typecheck` -> PASS
2. `docker compose exec -T backend ... pytest -q tests/test_bootstrap_session_api.py tests/test_auth.py tests/test_2fa_challenge.py` -> PASS (`15 passed`)

Guardias requeridos por gobernanza cross-domain:

1. `qa-architecture-dependency-guard` -> pendiente de corrida final en este cierre.
2. `qa-route-contract-guard` -> pendiente de corrida final en este cierre.
3. `qa-pr-blast-radius-guard` -> pendiente de corrida final en este cierre.
4. `qa-codex-governance-guard` -> se desbloquea con este handoff.

## Riesgos remanentes

1. Gate operativo externo aún pendiente:
   - certificación manual móvil HTTPS 7/7 en LAN/staging-prod.
2. Riesgo medio de drift entre shell base y rutas si no se mantiene bootstrap como única fuente en siguientes slices.
3. Riesgo bajo de regresión por contratos de ruta si se agregan endpoints auth sin actualizar baseline de guardias.

Mitigación:

1. Mantener el patrón bootstrap único en guardias privadas.
2. Ejecutar guardias cross-domain completos antes de merge.
3. No abrir trabajo de módulos finales hasta tener gate operativo móvil en PASS.

## Blast radius

Radio de impacto acotado a:

1. Backend auth (`accounts/views.py`, `accounts/urls.py`, middleware de contexto, pruebas nuevas de bootstrap).
2. Frontend sesión/ruteo/layout (`auth.store`, `session-bootstrap.store`, `router/index.ts`, `MainLayout.vue`, stores auxiliares ACL/contexto).

No impactado:

1. Dominios transaccionales de inventario/facturación/estación.
2. Contratos reporting/analytics.
3. Carril público de enroll y sincronización pública.
