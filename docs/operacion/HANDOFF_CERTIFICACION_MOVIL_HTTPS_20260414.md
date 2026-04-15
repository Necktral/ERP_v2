# HANDOFF - Certificación móvil HTTPS (2026-04-14)

Version: v1.0  
Fecha: 2026-04-14  
Tipo de cambio: `single_domain_code`  
Modo de ejecucion: auto edit

## Diagnostico del area

Con `b29625f4` el hardening técnico de auth móvil quedó implementado.  
El gap restante era operativo:

1. certificar matriz móvil real HTTPS (LAN y staging/prod),
2. cerrar brecha de validación automática en host local (DB) usando ejecución containerizada,
3. consolidar acta canónica de certificación para habilitar Fase 2.

## Alcance exacto

Incluido:

1. Acta canónica versionada de certificación móvil HTTPS con formato PASS/FAIL por entorno/caso.
2. Estandarización del comando de pruebas Django en backend container (`make qa-auth-mobile-cookie-tests`).
3. Ajustes mínimos de pruebas para cubrir transporte inseguro en cookie-auth y compatibilidad con envelope de error.
4. Actualización de índice/changelog y referencia cruzada en runbook de sesión móvil.

Excluido:

- Sin cambios en bootstrap/shells/módulos.
- Sin cambios de contratos HTTP públicos.
- Sin cambios de dominio transaccional.

## Contratos impactados

Sin cambios de API pública.

Se preserva:

- carril público de enroll (`/device/enroll`, `/api/sync/enroll/`, `/api/sync/batch/`),
- carril privado autenticado cookie+HTTPS,
- contratos canónicos de reporting/analytics vigentes.

## Pruebas / validación

Validaciones ejecutadas:

1. `make qa-auth-mobile-cookie-tests` -> PASS (`13 passed`).
2. `make qa-codex-governance-guard` -> PASS.
3. `make qa-route-contract-guard` -> PASS.
4. `make qa-readme-section-guard` -> PASS.
5. `make qa-pr-blast-radius-guard` -> PASS.

Artefacto principal:

- `qa/reports/auth_mobile_cookie_https_tests.txt`

## Riesgos remanentes

1. La certificación manual en dispositivo móvil real (LAN/staging-prod) sigue pendiente hasta capturar evidencia de campo 7/7 PASS.
2. Si el proxy TLS no propaga correctamente cabeceras de esquema, el backend puede no detectar `request.is_secure()` como esperado.
3. No se debe abrir Fase 2 (bootstrap) hasta cierre formal del acta con evidencia real.

