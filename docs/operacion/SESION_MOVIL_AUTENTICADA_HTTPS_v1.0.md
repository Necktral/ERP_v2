# SESION MOVIL AUTENTICADA HTTPS v1.0

## Objetivo

Cerrar de forma operativa y verificable la sesion autenticada en moviles para el carril privado del sistema web:

- `POST /api/auth/login/`
- `GET /api/auth/me/`
- `POST /api/auth/refresh/`
- navegacion privada y recarga sin perdida espuria de sesion.

Politica obligatoria en esta fase:

- **HTTPS obligatorio tambien en LAN** para autenticacion por cookie.
- El flujo publico de enrolamiento (`/device/enroll`, `/api/sync/enroll/`, `/api/sync/batch/`) se mantiene separado.

## Matriz efectiva por entorno

| Entorno | Esquema requerido | AUTH_COOKIE_SECURE | AUTH_COOKIE_REQUIRE_HTTPS | CORS/CSRF expected | Resultado esperado |
|---|---|---:|---:|---|---|
| Dev local (localhost) | `http` permitido para desarrollo | `0` | `0` | Origen `http://localhost:3000` | Puede autenticar localmente, sin garantia de comportamiento movil real |
| LAN operativo (movil real) | `https` obligatorio | `1` | `1` | Origen `https://<HOST>` | Sesion movil estable (login/me/refresh) |
| Staging/Prod | `https` obligatorio | `1` | `1` | Origenes HTTPS reales de frontend | Sesion estable + seguridad contractual |

## Causa raiz del patron login 200 + me/refresh 401

Causa principal:

- desalineacion entre transporte de sesion por cookie y contexto de acceso (http/cross-origin), especialmente en movil.

Factores que disparan el patron:

1. Acceso privado sin HTTPS real cuando se exige cookie segura.
2. `VITE_API_BASE_URL` apuntando a origen distinto en modo cookie.
3. Reintento global de refresh sobre endpoints publicos de enroll/sync.

## Cambios aplicados (fase de cierre)

1. Backend:
- Nueva bandera `AUTH_COOKIE_REQUIRE_HTTPS` (default seguro por entorno) para exigir HTTPS cuando el transporte es cookie.
- En login/refresh/logout/2FA verify, respuesta explicita `400` si se intenta cookie-auth en transporte inseguro y la politica esta activa.

2. Frontend:
- En modo cookie, si `VITE_API_BASE_URL` es cross-origin, fallback a `/api` para mantener same-origin de sesion.
- Se excluye refresh automatico en endpoints publicos (`/sync/enroll/`, `/sync/batch/`) y auth sensibles (`/auth/login/`, `/auth/refresh/`, `/auth/logout/`, `/auth/bootstrap/`).
- Advertencia explicita en consola cuando se detecta contexto no HTTPS fuera de localhost.

3. Entorno/documentacion:
- Ejemplo de produccion actualizado a origenes HTTPS.
- Variable `AUTH_COOKIE_REQUIRE_HTTPS` documentada.

## Certificacion PASS/FAIL (obligatoria)

Registrar evidencia por entorno con timestamp y `request_id`:

| Caso | Dev local | LAN HTTPS | Staging/Prod |
|---|---|---|---|
| Login `POST /api/auth/login/` = 200 | PASS/FAIL | PASS/FAIL | PASS/FAIL |
| Me `GET /api/auth/me/` = 200 tras login | PASS/FAIL | PASS/FAIL | PASS/FAIL |
| Refresh `POST /api/auth/refresh/` estable | PASS/FAIL | PASS/FAIL | PASS/FAIL |
| Recarga mantiene sesion privada | PASS/FAIL | PASS/FAIL | PASS/FAIL |
| Navegacion privada sin 401 espurios | PASS/FAIL | PASS/FAIL | PASS/FAIL |
| Enroll publico sigue operativo | PASS/FAIL | PASS/FAIL | PASS/FAIL |

Criterio de cierre:

- LAN HTTPS y Staging/Prod deben quedar en PASS completo.
- Si LAN intenta HTTP con `AUTH_COOKIE_REQUIRE_HTTPS=1`, el rechazo debe ser explicito y trazable (esperado).

## Que si / que no

Si:

- usar HTTPS para todo carril privado en movil.
- mantener `VITE_API_BASE_URL=/api` en despliegues cookie-auth.
- mantener CORS/CSRF alineado a origenes HTTPS reales.

No:

- no usar HTTP para sesion privada en LAN/Prod.
- no mezclar carril publico de enroll con autenticacion privada.
- no apuntar frontend movil a API cross-origin en cookie-mode.

## Contrato

- Sin cambios de contrato HTTP publico.
- Se preserva `/api/sync/*` para flujo publico y `/api/reporting/*` como carril canonico.
