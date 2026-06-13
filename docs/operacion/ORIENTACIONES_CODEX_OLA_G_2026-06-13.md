# Orientaciones para Codex — Ola G (Verticales) · 2026-06-13

**Para:** Codex (responsable de GitHub: commits, ramas, PRs).
**De:** Claude (construcción + verificación local; deja el árbol validado, no commitea).

Ola G **cierra el programa "todos los módulos al estándar" (Olas A–G)**. Son tres verticales,
cada uno = "agregar la capa que faltaba sobre un módulo ya robusto". Multi-empresa, UI en español,
tokens `--app-*`. **No toca el mayor (GL) ni centros de costo** (decisión del dueño: todo operativo).

## ✅ Estado de verificación (local, en dev)
- **Suite backend completa: exit 0** (sin fallas).
- Tests dirigidos nuevos: **17/17** (tanques 7 + costos flota 5 + presupuesto finca 5).
- Módulo finca solo: **25/25**. Typecheck + lint frontend: **limpios**.
- **E2E vivo `simulacion/e2e_ola_g.py`: 14/14** contra localhost:8000 (token Wis, company 2, branch 3).

## 📦 Inventario de archivos (esto es Ola G)

### Vertical 1 — Tanques de estación (`modulos/estacion_servicios`)
- NUEVO `tank_service.py`, `views_tanks.py`, `tests/test_tanks.py`,
  `migrations/0013_fueltank_fueltankmovement_and_more.py`
- MOD `models.py` (modelos `FuelTank`, `FuelTankMovement`), `urls.py` (rutas `tanks/...`),
  `services.py` (**hook ADITIVO** en `record_dispense`: descuenta del tanque activo del producto;
  **no-op si no hay tanque** → no altera el flujo de despacho existente; usa import perezoso).

### Vertical 2 — Costos de flota (`modulos/fleet`)
- NUEVO `services_costs.py`, `views_costs.py`, `tests/test_fleet_costs.py`,
  `migrations/0002_fleetexpense_fuellog_maintenanceworkorder.py`
- MOD `models.py` (`FuelLog`, `MaintenanceWorkOrder`, `FleetExpense`; **+`from django.conf import settings`**),
  `urls.py` (rutas `assets/<id>/fuel-logs|maintenance-orders|expenses|cost-summary/`).

### Vertical 3 — Presupuesto de finca (`modulos/finca`)
- NUEVO `services_budget.py`, `views_budget.py`, `tests/test_finca_budget.py`,
  `migrations/0004_fincabudget_fincabudgetline_and_more.py`
- MOD `models.py` (`FincaBudget`, `FincaBudgetLine`), `urls.py` (rutas `budgets/...`).

### Transversales (archivos COMPARTIDOS — ver caveats)
- MOD `modulos/audit/contracts.py` — bloque "Ola G" al final: eventos `FUEL_TANK_{CREATED,RECEIVED,
  ADJUSTED}`, `FLEET_{FUEL_LOG,MAINTENANCE,EXPENSE}_RECORDED`, `FINCA_BUDGET_{CREATED,APPROVED,ARCHIVED}`;
  subjects `FLEET_ASSET`(ya existía), `FLEET_COST`, `FINCA_BUDGET`.
- MOD `modulos/rbac/seed_v01.py` — **4 permisos nuevos**: `fleet.cost.{read,manage}`,
  `finca.budget.{read,manage}` (asignados a company_admin + roles de flota/finca). **OJO:**
  `fuel.tank.{read,receive,adjust}` **ya existían** en el seed (anticipados) — NO los agregué, los reuso.
- `org/module_catalog.py`: **SIN cambios** (los 3 módulos ya estaban registrados).

### Frontend
- MOD `features/fuel/fuel.api.ts`, `features/fleet/fleet.api.ts`, `features/finca/finca.api.ts` (funciones nuevas).
- NUEVO `pages/estacion/TanquesPage.vue`, `pages/flota/CostosFlotaPage.vue`, `pages/finca/PresupuestoFincaPage.vue`.
- MOD `pages/estacion/EstacionPage.vue` (+botón Tanques), `pages/flota/FlotaPage.vue` (+botón Costos),
  `pages/finca/FincaPage.vue` (+botón Presupuesto), `router/routes.ts` (3 rutas).

### Simulación
- NUEVO `simulacion/e2e_ola_g.py`.

## ⚠️ Caveats críticos antes de commitear
1. **El árbol está mezclado.** Además de Ola G, hay trabajo sin commitear de olas previas (B–F) y
   **tu propio "complemento de salario"** (`hr 0011`, `nómina 0014`, modelos/serializers hr/nómina).
   **Ola G es su propia unidad lógica** — no la mezcles con el complemento de salario.
2. **Archivos compartidos** (`audit/contracts.py`, `rbac/seed_v01.py`, `router/routes.ts`): tocados por
   varias olas. Al commitear Ola G, incluí **solo** sus bloques (están identificables: los de Ola G van
   al final / con comentario "Ola G"). `audit/contracts.py` fue **reformateado por un linter** durante
   la sesión; verificá que las 9 entradas de eventos + 3 subjects de Ola G sigan presentes (al final del archivo).
3. **Migraciones scopeadas a propósito:** corrí `makemigrations estacion_servicios fleet finca`
   (NO hr/nómina) justamente para **no chocar** con tus migraciones del complemento de salario.
   Numeración: estacion_servicios **0013**, fleet **0002**, finca **0004**.
4. **Secretos en repo:** siguen siendo intencionales para la fase de IA-dev (rotar antes de prod). No los toques.

## 📝 Commit sugerido (mensaje)
```
feat(verticales): Ola G — tanques de estación, costos de flota y presupuesto de finca

- estación: control básico de tanques (nivel + recepciones + ajustes), descuento
  automático por despacho (hook aditivo, no-op sin tanque); reusa perms fuel.tank.*
- flota: costos reales por activo (combustible con consumo km/L, mantenimiento con
  costo, gastos) + resumen costo/km; registro manual; perms fleet.cost.*
- finca: presupuesto por labor×lote×ciclo + presupuesto-vs-real (jornales×tarifa +
  insumos) con SoD en aprobar; perms finca.budget.*
- migraciones: estacion_servicios 0013, fleet 0002, finca 0004
- NO imputa al GL/centros de costo (operativo, por decisión del dueño)

Verificado: suite backend exit 0, dirigidos 17/17, E2E 14/14, typecheck/lint OK.
```

## 🔧 Post-merge (aplicar en cada entorno)
```bash
# dentro del contenedor backend, PYTHONPATH=/app/backend/src, DJANGO_SETTINGS_MODULE=config.settings.base
python src/manage.py migrate estacion_servicios
python src/manage.py migrate fleet
python src/manage.py migrate finca
python src/manage.py seed_rbac_v01     # idempotente; siembra fleet.cost.* y finca.budget.*
```

## 🧠 Notas para el PR / lecciones
- **Decisiones de alcance del dueño:** tanques BÁSICO (sin varillaje/conciliación de mermas), flota
  costos MANUALES (sin enlace automático a la estación), finca por labor×lote×ciclo, **sin tocar el GL**.
- **Lección de tests (no es bug):** las pruebas finca GL (`test_gl_inventory`, `test_field_link`) **fallan
  si se corren en un batch parcial junto a `rbac`** (el test de seed resetea permisos y contamina el estado),
  pero **pasan solas (finca 25/25) y en la suite completa (exit 0)**. El gate real es la suite completa.
- El programa A–G queda **cerrado**. Futuro anotado (a la orden del dueño): imputar costos de flota/finca
  al mayor vía los centros de costo de Ola E, y el módulo `manejo_finca` (cuadrillas/zonas/tareas).
