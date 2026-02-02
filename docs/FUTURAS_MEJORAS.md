# Futuras mejoras — Roadmap técnico/funcional

Versión: v1.0  
Fecha: 2026-01-26  
Estado: **Backlog de mejoras (vivo)**

## Objetivo

Capturar mejoras futuras del sistema (técnicas y de producto) para que queden **versionadas** y alineadas con:

- auditoría contractual,
- RBAC/multiempresa,
- operación offline-first (sync engine),
- QA Gates (CI determinista).

## Principios (para decidir prioridades)

- **Seguridad e integridad primero:** auditoría, permisos, trazabilidad.
- **Operación primero:** cierres, conciliaciones, reportes reproducibles.
- **Offline-first real:** el móvil no “se rompe” sin internet; solo degrada.
- **Determinismo:** cada regla crítica debe tener test (y pasar en CI).

## Mejoras por horizonte

### A) Corto plazo (1–4 semanas)

1. **Documentación normativa completa**

- Completar el texto normativo del Contract Pack y del Addendum offline-first dentro de los documentos oficiales.
- Añadir un mini “glosario” de términos (company/branch, receipt, command, outbox, cierre, conciliación).

2. **Contrato de errores y códigos (API)**

- Estandarizar respuestas de error (códigos/reason_code) por endpoint.
- Mantener coherencia entre `reason_code` de auditoría y errores HTTP.

3. **Observabilidad mínima**

- ✅ Implementado (2026-02-02): correlación por request (`request_id`) y logging estructurado.
- ⏳ Pendiente: métricas básicas (latencias por endpoint, tasa de 401/403, tasa de 5xx).

4. **Hardening de seguridad**

- ✅ Implementado (2026-02-02): rate limiting coherente en endpoints sensibles.
- ⏳ Pendiente: rotación/gestión de secretos (AUDIT_HMAC_KEY, claves de firma, etc.).

### B) Mediano plazo (1–3 meses)

1. **Billing Kernel (facturación) como kernel reutilizable**

- Modelar documentos (p.ej. invoice/credit note), estados y transiciones.
- Auditoría por operación (create/void/refund/reprint/export).
- API con permisos RBAC por método (read/write/void).

2. **Inventory Kernel (inventarios) con trazabilidad**

- Kardex/movimientos como “fuente de verdad”.
- Recepciones, ajustes, transferencias, conteos cíclicos.
- Integración con FUEL (descargas a tanque como movimiento de inventario).

3. **Outbox de integración**

- Outbox transaccional (misma TX que el cambio de dominio).
- Reprocesamiento idempotente y visible (RBAC + auditoría).

4. **Sync engine — device_seq + huecos + reconciliación**

- `device_seq` monotónico por dispositivo.
- Detección de huecos (missing seq) y estrategia de recuperación.
- Cuarentena/revocación automática ante anomalías (firma inválida repetida, skew extremo, etc.).

### C) Largo plazo (3–9 meses)

1. **AR/AP/Tesorería**

- Cuentas por cobrar/pagar, pagos parciales, conciliación bancaria.
- Integración con Billing (documentos) e Inventory (costos).

2. **Motor de reportes formal**

- Reportes reproducibles (misma entrada => misma salida).
- Exportación segura (RBAC + auditoría + marcas de agua).

3. **Móvil robusto (operación offline real)**

- UI/UX para colas offline (pendientes/enviados/rechazados).
- Reintentos con backoff, manejo de conflictos y resolución guiada.

## Mejoras específicas por área

### Dominio FUEL (Estación de Servicios)

- Tanques y boquillas: calibración, mermas, conciliación por turno.
- Precios por producto + vigencias + auditoría de cambios.
- Anulación/cancelación con reglas (por ventana de tiempo y roles).
- Integración contable: cierres generan asientos (vía Billing/Treasury).

### Auditoría contractual

- Clasificar eventos por severidad y criticidad.
- Exportación segura de auditoría (con filtros por scope).
- “Playbook” de incidentes: qué revisar si falla integridad.

### QA / CI

- Aumentar cobertura de tests en áreas críticas (auditoría, RBAC, sync).
- Perf tests básicos para endpoints con listados (paginación, índices).

## Backlog “nice to have”

- Feature flags por company/branch.
- Auditoría de lectura en endpoints críticos (configurable).
- Soporte de multi-moneda y rounding controlado por reglas.

---

Notas:

- Este backlog no reemplaza issues; sirve como guía de producto/arquitectura.
- Cuando una mejora se implemente, registrar en CHANGELOG/BITACORA y enlazar el PR.
