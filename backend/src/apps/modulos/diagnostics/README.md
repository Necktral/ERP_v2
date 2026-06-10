# Módulo `diagnostics` — plataforma de diagnóstico (Mundo B)

Capacidad de **ingeniería/observabilidad** (no cara al usuario del ERP). Convierte los
errores de runtime en un **ledger de evidencia consultable**. Diseño completo en
`docs/design/AI_DIAGNOSTIC_PLATFORM_SPINE_20260610.md`.

> Principio: **evidencia primero, sin IA; los gates bloquean; la IA llega al final.**

## Rebanada B-1 (esta) — `ErrorEvent`
- **Captura automática y best-effort:** un receiver de `got_request_exception` (`capture.py`)
  persiste cada error 500 no manejado. **Nunca altera la respuesta** (todo en try/except, igual
  que el tag de Sentry en `config/middleware/request_id.py`).
- **Dedupe por `stack_hash`:** mismo stack ⇒ misma fila con `occurrence_count++` (no inunda la tabla).
- **Clasificación Necktral:** `domain_map.py` mapea el frame más profundo del repo a un dominio y a
  su clase de riesgo **C1/C2/C3** (dinero/stock/fiscal/permisos/CEC/auditoría = C1).
- **Redacción (J2):** la traza guarda SOLO frames (sin el mensaje crudo, que va hasheado) y se le pasa
  un scrub de `clave=valor` sensibles (`extract.py`).
- **Trazabilidad (J1):** cada evento lleva `correlation_id` (del `X-Request-Id`) + `domain` + `risk_class`.

## API de lectura (ops; permiso `diagnostics.error.read`)
- `GET /api/diagnostics/errors/` — lista (filtros `domain`, `risk_class`, `status`).
- `GET /api/diagnostics/errors/<error_id>/` — detalle (incluye la traza redactada).

## Fuera de esta rebanada (siguientes)
`SecurityFinding` (B-2), `CodeUnitEvidence` (B-3), gates `evidence-c1-guard`/`regression-sentinel`
(B-4), diagnóstico IA advisory (B-5); tenant-scoping fino del read API; OpenTelemetry/traces.
