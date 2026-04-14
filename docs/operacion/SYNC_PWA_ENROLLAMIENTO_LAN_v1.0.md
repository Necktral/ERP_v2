# SYNC PWA ENROLLAMIENTO LAN v1.0

## Objetivo
Establecer un procedimiento operativo, reproducible y no-breaking para ejecutar el flujo real de enrolamiento de dispositivos por QR/PWA en red LAN:
`challenge -> enroll -> batch` desde teléfono, sin app nativa.

## Configuración requerida
Fuente de verdad: variables de entorno consumidas por `backend` y `frontend` en Docker.

- `SYNC_ENROLL_WEB_BASE_URL=http://<IP_HOST>:3000`
- `VITE_API_BASE_URL=http://<IP_HOST>:8000/api`
- `DJANGO_ALLOWED_HOSTS` debe incluir `<IP_HOST>`
- `DJANGO_CORS_ALLOWED_ORIGINS` debe incluir `http://<IP_HOST>:3000`
- `DJANGO_CSRF_TRUSTED_ORIGINS` debe incluir `http://<IP_HOST>:3000`

Ejemplo LAN local:

```env
SYNC_ENROLL_WEB_BASE_URL=http://172.31.136.92:3000
VITE_API_BASE_URL=http://172.31.136.92:8000/api
DJANGO_ALLOWED_HOSTS=localhost,127.0.0.1,backend,172.31.136.92
DJANGO_CORS_ALLOWED_ORIGINS=http://localhost:3000,http://172.31.136.92:3000
DJANGO_CSRF_TRUSTED_ORIGINS=http://localhost:3000,http://172.31.136.92:3000
```

Notas:
- `.env` local no se versiona.
- Si cambia la IP LAN, actualizar estas variables y reiniciar servicios.

## Arranque Docker (backend/frontend)

```bash
docker compose up -d backend frontend
docker compose ps backend frontend
```

Criterio:
- `backend` en `healthy`
- `frontend` en `Up`
- Política de reinicio esperada: `unless-stopped`

Verificación rápida:

```bash
curl -I http://localhost:3000
curl -I http://<IP_HOST>:3000
docker inspect -f '{{.HostConfig.RestartPolicy.Name}}' erpcrm_frontend
```

## Ejecución real (teléfono + backoffice)

1. Ingresar al backoffice y abrir `Sincronización -> Enrolamiento`.
2. Generar challenge en `/api/sync/enrollment/challenges/`.
3. Verificar que `enrollment_uri` sea tipo:
   - `http://<IP_HOST>:3000/#/device/enroll?code=...`
4. Escanear QR con el teléfono (misma red WiFi que el host).
5. Confirmar apertura de la ruta pública PWA `#/device/enroll`.
6. Ejecutar enrolamiento y batch desde la PWA:
   - `POST /api/sync/enroll/` esperado: `201`
   - `POST /api/sync/batch/` esperado: `200` con resultado `APPLIED` o `DUPLICATE`

## Trazabilidad obligatoria
Validar correlación por request y auditoría:

- `trace.request_id`
- `trace.audit_event_id` (challenge/enroll)
- Eventos esperados en auditoría:
  - `SYNC_ENROLL_CHALLENGE_CREATED`
  - `SYNC_DEVICE_ENROLLED`
  - `SYNC_BATCH_RECEIVED` y/o `SYNC_COMMAND_APPLIED`

Checklist de correlación mínima:
- `request_id` de respuesta aparece en logs de aplicación.
- `audit_event_id` resuelve al evento correcto en bitácora.
- `device_id` del batch coincide con el enrolado.

## Troubleshooting exacto

### 1) QR apunta a `localhost`
**Síntoma**: en el teléfono abre navegador pero no carga correctamente el flujo esperado.

**Causa raíz**: `SYNC_ENROLL_WEB_BASE_URL` quedó en `http://localhost:3000`.

**Fix**:
- ajustar `SYNC_ENROLL_WEB_BASE_URL` a `http://<IP_HOST>:3000`
- recrear backend
- generar challenge nuevo

### 2) `login=200` pero `GET /auth/me` y `POST /auth/refresh` dan `401`
**Causa frecuente**: cookies no reenviadas por navegador móvil (restricción de privacidad/cookies o residuos de sesión).

**Acción**:
- limpiar datos del sitio para `http://<IP_HOST>:3000` y `http://<IP_HOST>:8000`
- reintentar
- para enrolamiento PWA, usar directamente `#/device/enroll` (ruta pública), no forzar flujo de login

### 3) No usar login para `/device/enroll`
`/device/enroll` está diseñado para operación pública controlada de alta de dispositivo. El login web no es requisito para ese paso.

### 4) Compatibilidad WebCrypto/Ed25519
Algunos dispositivos/navegadores exigen contexto seguro para operaciones criptográficas avanzadas.

- En LAN HTTP puede funcionar según navegador.
- Si falla generación/firma en móvil, mover prueba real a staging HTTPS.

## Checklist de cierre operativo

PASS si:
- `backend/frontend` arriba y accesibles
- `enrollment_uri` usa `<IP_HOST>` (no localhost)
- `enroll=201`
- `batch=200` con `APPLIED|DUPLICATE`
- trazabilidad completa (`request_id` + `audit_event_id` + auditoría)

FAIL/BLOCK si:
- QR sigue resolviendo a localhost
- no hay conectividad teléfono-host
- fallo criptográfico no soportado en navegador objetivo
- no hay correlación de auditoría

## Contrato/API
- Sin cambios de contrato HTTP público en `/api/sync/*`.
- El ajuste aplicado es de infraestructura frontend: `VITE_API_BASE_URL` parametrizable por `.env` en Docker.
