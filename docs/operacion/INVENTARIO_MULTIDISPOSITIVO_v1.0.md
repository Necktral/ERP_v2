# INVENTARIO MULTIDISPOSITIVO (CORE OPERACIONAL) v1.0

Version: v1.0  
Fecha: 2026-04-14  
Estado: Diseno funcional ejecutable (internet-first, no-breaking)

## Resumen

Este documento define el modulo de inventarios para uso en laptop/PC y movil bajo una sola logica de negocio backend.

Politicas base de esta fase:

- alcance `core operacional` (sin lotes/series/caducidad),
- costeo por promedio movil,
- stock negativo bloqueado por defecto,
- UX dual-shell:
  - `Workbench` para desktop (operacion densa + analitica),
  - `Taskflow` para movil (ejecucion rapida + validacion corta).

## 1) Objetivo del modulo

- Controlar existencias y valoracion por bodega/sucursal de forma trazable y auditable.
- Garantizar que toda mutacion sea idempotente, contextual y consistente.
- Permitir operacion rapida en movil sin sacrificar control y analitica en desktop.

## 2) Operaciones principales

| Operacion | Tipo | Laptop/PC | Movil | Resultado esperado |
|---|---|---|---|---|
| Crear bodega | Captura maestra | Si | No | Bodega operativa por sucursal |
| Crear item | Captura maestra | Si | No | SKU disponible para movimientos |
| Recepcion | Captura + confirmacion transaccional | Si | Si | Incrementa stock y recalcula costo promedio |
| Salida | Captura + confirmacion transaccional | Si | Si | Reduce stock; bloquea si insuficiente |
| Ajuste | Captura + confirmacion transaccional | Si | Si (acotado) | Corrige stock con motivo obligatorio |
| Transferencia | Captura + confirmacion transaccional | Si | Si (guiado) | Salida origen + entrada destino |
| Consulta balance | Solo lectura | Si | Si | `qty_on_hand` y `avg_cost` actuales |
| Historial/Kardex | Solo lectura analitica | Si | Si (resumido) | Trazabilidad de movimientos |

## 3) Que se hace desde laptop

- Altas maestras: bodegas, SKUs, UoM operativa.
- Operaciones densas: ajustes complejos, transferencias multiples, conciliacion.
- Consulta analitica: historial detallado, variaciones, auditoria cruzada.
- Gestion de excepciones y regularizaciones.

## 4) Que se hace desde movil

- Recepciones, salidas, ajustes simples y transferencias guiadas.
- Consulta rapida de stock por bodega/item.
- Confirmaciones transaccionales en 3-5 pasos.
- Reintento seguro por idempotencia (`command_id`/`idempotency_key`).

## 5) Flujos criticos

### Flujo 1: Recepcion

1. Seleccionar contexto activo.
2. Escanear/buscar item.
3. Ingresar cantidad y costo.
4. Confirmar operacion.

Validaciones: contexto valido, `qty > 0`, `unit_cost >= 0`, idempotencia.

### Flujo 2: Salida

1. Seleccionar contexto activo.
2. Buscar item y cantidad.
3. Confirmar operacion.

Validaciones: `qty > 0`, stock suficiente, idempotencia.

### Flujo 3: Ajuste

1. Contexto activo.
2. Item y nuevo stock.
3. Motivo obligatorio.
4. Confirmacion reforzada.

Validaciones: `new_qty_on_hand >= 0`, motivo obligatorio, idempotencia.

### Flujo 4: Transferencia

1. Seleccionar bodega origen y destino.
2. Seleccionar item y cantidad.
3. Confirmar transaccion.

Validaciones: origen != destino, `qty > 0`, stock suficiente en origen, idempotencia.

### Flujo 5: Consulta operativa

1. Filtro rapido por bodega/item.
2. Lectura de existencia y costo promedio.

## 6) Pantallas recomendadas

### Workbench (desktop)

- `Inventario > Dashboard Operativo` (KPI stock, quiebres, ajustes pendientes).
- `Bodegas` (ABM).
- `Items/SKU` (ABM + busqueda avanzada).
- `Movimientos` (recepcion/salida/ajuste/transferencia con tabla densa).
- `Kardex y conciliacion` (filtros avanzados, export, auditoria).

### Taskflow (movil)

- `Inicio Inventario` (acciones rapidas).
- `Recibir stock` (wizard corto).
- `Emitir salida` (wizard corto).
- `Ajustar stock` (wizard con motivo obligatorio).
- `Transferir` (wizard origen-destino).
- `Consultar stock` (lectura resumida).

## 7) Reglas de validacion

- `company_id` y `branch_id` obligatorios en toda mutacion.
- `warehouse_id` e `item_id` deben existir y pertenecer al contexto.
- `qty > 0` en recepciones/salidas/transferencias.
- Ajuste requiere `new_qty_on_hand >= 0` y motivo obligatorio.
- Transferencia requiere origen != destino.
- Idempotencia obligatoria por `command_id`/`idempotency_key`.
- Stock insuficiente bloquea salida por defecto.
- Cuantizacion canonica: qty 4 decimales, costo 6 decimales.

## 8) Reglas de permisos

- `inventory.warehouse.create` para crear bodegas.
- `inventory.item.create` para crear items.
- `inventory.movement.receive` para recepcion.
- `inventory.movement.issue` para salida.
- `inventory.movement.adjust` para ajuste.
- `inventory.transfer.create` para transferencia.
- `inventory.balance.read` para consulta de balance.

Regla recomendada (futuro): permiso elevado para excepciones de stock negativo con motivo/aprobacion/auditoria obligatoria.

## 9) Trazabilidad requerida

Cada operacion transaccional DEBE registrar:

- `request_id`, `audit_event_id`, `actor_id`, `company_id`, `branch_id`,
- `source_device`, `channel`, `command_id`,
- entidad afectada: `warehouse_id`, `item_id`, `movement_id`,
- resultado contable: estado, error, enlace a draft/asiento (cuando exista).

Regla de seguridad: NO registrar secretos ni datos sensibles innecesarios en logs/eventos.

## 10) Errores operativos frecuentes

- Contexto incorrecto (empresa/sucursal equivocada).
- Doble envio por reintento sin idempotencia efectiva.
- Stock insuficiente en salida.
- Transferencia con origen/destino incorrectos.
- Ajustes sin motivo trazable.
- Desfase entre operacion fisica y registro digital.
- Permiso insuficiente en accion de alto impacto.

## 11) Recomendaciones UX por dispositivo

### Desktop

- Tablas densas con filtros compuestos y guardado de vistas.
- Acciones por lote con resumen de impacto.
- Drill-down a auditoria y contabilidad asociada.

### Movil

- Una accion primaria por pantalla.
- Formularios cortos, defaults inteligentes, busqueda rapida/escaneo.
- Mensajes accionables: `Reintentar`, `Corregir dato`, `Cambiar contexto`.
- Estados recuperables obligatorios: sesion expirada, permiso denegado, timeout/red.

---

## Cambios de interfaces/tipos (aditivos, no-breaking)

### Metadata minima de comando

- `company_id`
- `branch_id`
- `command_id`
- `source_device`
- `channel`
- `device_class`

### Bloque `trace` minimo de respuesta

- `trace.request_id`
- `trace.audit_event_id`
- `trace.channel`
- `trace.source_device`

### Catalogo unico de errores de inventario

- `error_code`
- `cause`
- `recommended_action`

## Plan de pruebas y escenarios

1. Paridad funcional desktop vs movil para operaciones equivalentes.
2. Idempotencia: reenvio de mismo `command_id` no duplica movimientos.
3. Validaciones criticas:
   - stock insuficiente bloquea salida,
   - transferencia invalida (mismo origen/destino) se rechaza.
4. Permisos: pruebas positivas/negativas por rol y contexto.
5. Trazabilidad E2E: correlacion entre respuesta (`trace`), logs y auditoria.
6. UX movil: flujos criticos completables en <= 5 pasos y con recuperacion.

## Supuestos y defaults

- Fase actual: inventario core operacional, sin lotes/series/caducidad.
- Costeo: promedio movil por bodega/item.
- Politica de stock: bloqueo por defecto cuando no hay existencias suficientes.
- Conectividad movil: online-first + retry (sin offline amplio).
- Arquitectura: dual-shell UX con una sola logica de negocio backend.

## Mapeo de API actual (referencial)

- `POST /api/inventory/warehouses/`
- `POST /api/inventory/items/`
- `POST /api/inventory/movements/receive/`
- `POST /api/inventory/movements/issue/`
- `POST /api/inventory/movements/adjust/`
- `POST /api/inventory/transfers/`
- `GET /api/inventory/balances/`
