# Addendum Offline-first v1.0 — Sync, idempotencia y auditoría offline

Versión: v1.0  
Fecha: 2026-01-26  
Estado: **Guía de organización (viva)**

## Propósito

Definir reglas para operación con móviles **con o sin internet**, garantizando:

- consistencia (idempotencia y deduplicación),
- seguridad (firma/verificación),
- trazabilidad (auditoría contractual),
- límites operativos (tamaños, batches, tolerancias).

## Precedente existente en el repo (lo que ya está implementado)

El repo ya incluye un motor de sync (`sync_engine`) con un contrato claro:

- Enrollment: basado en sesión/JWT y scope.
- Batch: autenticación por dispositivo + firma Ed25519 por comando.
- Mensaje de firma determinista (sin ambigüedad JSON).
- Idempotencia por `command_id`.

Referencias del repo:

- Serializers y contrato: `login_module/src/apps/sync_engine/serializers.py`
- Vistas: `login_module/src/apps/sync_engine/views.py`
- Servicios/idempotencia: `login_module/src/apps/sync_engine/services.py`

## Contrato offline-first (normativo)

### 1) Comandos como unidad de sincronización

- Cada cambio de estado en el dominio viaja como **comando** (no como “estado final”).
- Cada comando debe tener:
  - `command_id` (idempotencia)
  - `occurred_at` (tiempo del dispositivo, canonizado)
  - `payload` (schema validable)
  - `signature` (Ed25519)

### 2) Idempotencia y deduplicación

- El servidor debe tratar `command_id` como clave única.
- Reintentos por mala red deben resultar en **DUPLICATE** sin aplicar dos veces.

### 3) Lotes (batch)

- El cliente envía lotes acotados por tamaño y cantidad.
- El servidor devuelve un receipt con conteos y resumen de errores.

> Nota: los límites exactos deben mantenerse consistentes con la policy del backend.

### 4) Auditoría

- Operaciones aplicadas/rechazadas deben quedar trazadas.
- Si un comando genera efectos en un kernel/módulo, debe emitir los eventos contractuales correspondientes.

Referencia del contrato de auditoría:

- `login_module/src/apps/audit/contracts.py`

## Extensiones recomendadas (pendientes / por implementar)

Estas extensiones son típicas en offline-first y están contempladas como guía de evolución:

- `device_seq`: secuencia monotónica por dispositivo para detectar huecos.
- Outbox de integración: cola de eventos/deltas entre módulos o hacia terceros.
- Quarantine: bloqueo temporal de dispositivos con comportamiento anómalo.

> Pendiente: pegar aquí el texto completo del Addendum Offline-first provisto (reglas P7/P8, outbox, device_seq, reconciliación, etc.).

## Checklist para nuevos kernels (Billing/Inventory/...)

- Definir comandos y schemas (versionados).
- Asegurar idempotencia por `command_id`.
- Emitir auditoría contractual por operación.
- Respetar scope multiempresa.
- Añadir tests de sync + auditoría en el estilo existente.

---

Si vas a modificar este documento: mantener la versión y agregar un changelog breve al final.
