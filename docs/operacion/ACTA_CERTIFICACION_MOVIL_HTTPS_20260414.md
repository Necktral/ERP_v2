# ACTA CERTIFICACION MOVIL HTTPS (2026-04-14)

## Encabezado

- Version: v1.0
- Fecha: 2026-04-14
- Estado: PENDIENTE DE CIERRE OPERATIVO (requiere evidencia en movil real)
- Owner: Producto + Backend + Frontend + Operaciones
- Referencia tecnica: `b29625f4` (`auth móvil: exige HTTPS cookie, aísla refresh público y certifica operación LAN/Prod`)

## Alcance certificado

- Carril privado autenticado por cookie:
  - `POST /api/auth/login/`
  - `GET /api/auth/me/`
  - `POST /api/auth/refresh/`
  - recarga y navegacion privada
- No regresion en carril publico:
  - `/device/enroll`
  - `/api/sync/enroll/`
  - `/api/sync/batch/`

## Evidencia automatizada (container backend)

- Comando canónico: `make qa-auth-mobile-cookie-tests`
- Resultado de suite focalizada: PASS (13 passed)
- Artefacto: `qa/reports/auth_mobile_cookie_https_tests.txt`
- Nota: esta evidencia valida backend/auth en entorno containerizado y cierra la brecha de ejecucion host-local con PostgreSQL.

## Matriz de certificacion operativa (movil real, HTTPS)

Formato obligatorio por caso: fecha/hora, dispositivo, navegador, URL, request_id (si aplica), PASS/FAIL, evidencia breve.

| Entorno | Caso | Estado | Evidencia |
|---|---|---|---|
| LAN HTTPS | Apertura frontend `https://<host>` | FAIL | Pendiente ejecucion en movil real |
| LAN HTTPS | Login `POST /api/auth/login/` = 200 | FAIL | Pendiente ejecucion en movil real |
| LAN HTTPS | Me `GET /api/auth/me/` = 200 tras login | FAIL | Pendiente ejecucion en movil real |
| LAN HTTPS | Refresh `POST /api/auth/refresh/` estable | FAIL | Pendiente ejecucion en movil real |
| LAN HTTPS | Recarga conserva sesion privada | FAIL | Pendiente ejecucion en movil real |
| LAN HTTPS | Navegacion privada sin 401 espurios | FAIL | Pendiente ejecucion en movil real |
| LAN HTTPS | Enroll publico sigue operativo | FAIL | Pendiente ejecucion en movil real |
| Staging/Prod HTTPS | Apertura frontend `https://<host>` | FAIL | Pendiente ejecucion en movil real |
| Staging/Prod HTTPS | Login `POST /api/auth/login/` = 200 | FAIL | Pendiente ejecucion en movil real |
| Staging/Prod HTTPS | Me `GET /api/auth/me/` = 200 tras login | FAIL | Pendiente ejecucion en movil real |
| Staging/Prod HTTPS | Refresh `POST /api/auth/refresh/` estable | FAIL | Pendiente ejecucion en movil real |
| Staging/Prod HTTPS | Recarga conserva sesion privada | FAIL | Pendiente ejecucion en movil real |
| Staging/Prod HTTPS | Navegacion privada sin 401 espurios | FAIL | Pendiente ejecucion en movil real |
| Staging/Prod HTTPS | Enroll publico sigue operativo | FAIL | Pendiente ejecucion en movil real |

## Criterio de cierre para abrir Fase 2 (bootstrap)

Se habilita Fase 2 unicamente cuando:

1. LAN HTTPS: 7/7 casos en PASS.
2. Staging/Prod HTTPS: 7/7 casos en PASS.
3. Evidencia versionada con metadatos completos por caso.
4. Guardias minimos en PASS:
   - `make qa-codex-governance-guard`
   - `make qa-route-contract-guard`
   - `make qa-readme-section-guard`
   - `make qa-pr-blast-radius-guard`
