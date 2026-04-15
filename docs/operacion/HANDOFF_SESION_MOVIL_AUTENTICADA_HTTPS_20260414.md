# HANDOFF - Cierre de sesión móvil autenticada HTTPS (2026-04-14)

Version: v1.0  
Fecha: 2026-04-14  
Tipo de cambio: `cross_domain`  
Modo de ejecucion: auto edit

## Diagnostico del area

Se observó patrón operativo en móvil: `login 200` seguido de `GET /auth/me 401` y `POST /auth/refresh 401`.

Diagnóstico confirmado:

1. El flujo público de enroll ya está implementado y funcional.
2. El cuello de botella estaba en sesión privada móvil por cookie (entorno + base URL + retry global).
3. Faltaba política explícita de HTTPS obligatorio en carril privado para LAN/Prod.
4. El frontend permitía configuración cross-origin en `VITE_API_BASE_URL` en modo cookie y reintento de refresh en endpoints públicos.

## Alcance exacto

Incluido:

1. Endurecimiento backend para exigir HTTPS en cookie-auth cuando la política está activa.
2. Hardening frontend para sesión cookie same-origin y exclusión de refresh automático en endpoints públicos.
3. Documentación operativa de certificación móvil HTTPS + actualización de ejemplos `.env` y runbooks.

Excluido:

- No se modificaron contratos HTTP públicos.
- No se implementaron shells desktop/mobile ni módulos funcionales nuevos.
- No se tocaron migraciones ni dominios transaccionales fuera del carril de autenticación/config.

## Contratos impactados

Sin cambios de contrato de API.

Contratos preservados:

- flujo público `/api/sync/enroll/` y `/api/sync/batch/`,
- carril canónico `/api/reporting/*`,
- analytics `/analytics` + `8050` + same-origin.

## Pruebas / validación

Validaciones ejecutadas:

1. `python3 -m compileall -q backend/src/apps/modulos/accounts backend/src/config/settings backend/src/config/middleware`
2. `make qa-backend-ruff` (PASS)
3. `make qa-route-contract-guard` (PASS)
4. `make qa-codex-governance-guard` (PASS tras agregar este handoff)

Limitación conocida:

- No se ejecutó certificación móvil real en dispositivo físico desde esta sesión.
- El test de backend que requiere DB local de host falló previamente por credenciales de PostgreSQL del entorno local, no por el código del cambio.

## Riesgos remanentes

1. Si un despliegue LAN mantiene HTTP para carril privado con `AUTH_COOKIE_REQUIRE_HTTPS=1`, la autenticación será rechazada (esperado por política).
2. Si el reverse proxy no preserva cabeceras TLS correctamente, `request.is_secure()` puede no resolver como esperado.
3. Sigue pendiente certificación final en móvil real (PASS/FAIL) con evidencia de request_id en entorno objetivo.

Siguiente paso recomendado:

- ejecutar matriz de certificación móvil HTTPS del runbook `SESION_MOVIL_AUTENTICADA_HTTPS_v1.0.md` en LAN y staging/prod.
