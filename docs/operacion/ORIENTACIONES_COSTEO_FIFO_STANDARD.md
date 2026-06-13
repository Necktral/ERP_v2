# Motor de costeo FIFO/STANDARD (Unit #4) — orientación para empaquetado

**Rama:** `feat/inventory-costing-engine-v2` (worktree aislado sobre `31c9b7af`).
**Por qué:** el árbol ya tenía la política de costo versionada (`InventoryCostPolicy`,
invariante #8) y `resolve_costing_method`, pero las 4 rutas de posteo de
`kernels/inventarios/services.py` **solo aplicaban promedio móvil** y nunca ramificaban por
método. Este paquete **cablea el método al posteo**: FIFO real por capas y STANDARD con
varianza de compra. El default (sin política configurada) sigue siendo promedio ponderado
móvil — **comportamiento histórico intacto** (probado).

## Qué cambia

- **Modelos** (`inventarios/models.py`):
  - `InventoryItem.standard_cost` (Decimal 18,6) — costo estándar por unidad base.
  - `StockMovement.cost_variance` (Decimal 18,6) — varianza de compra sellada bajo STANDARD.
  - `StockMovementCostLayer` — libro de capas FIFO (company/branch/warehouse/item/lot,
    `source_movement`, `unit_cost`, `qty_initial`, `qty_remaining`, `created_at`); índice
    FIFO `ix_costlayer_fifo` y checks de cantidad.
  - **Migración:** `0010_inventoryitem_standard_cost_and_more.py` (depende de `0009`). En el
    worktree no hay colisión: la última committeada en `31c9b7af` es `0009`.
- **Motor** (`inventarios/costing.py`): `fifo_create_layer`, `fifo_consume` (consume las
  capas más antiguas y devuelve el COGS unitario ponderado; faltante → `fallback`),
  `fifo_weighted_cost` (mantiene `bal.avg_cost` = Σ capas / Σ qty).
- **Cableado** (`inventarios/services.py`) en `post_receive`, `post_issue`, `post_adjust`,
  `post_transfer`, al inicio resuelven `resolve_costing_method(company, branch)`:
  - **WEIGHTED_AVERAGE** (default): sin cambios.
  - **STANDARD**: inventario valuado al estándar; entrada registra varianza
    `(costo_real − estándar) × qty` en `cost_variance`; COGS de salida = estándar.
  - **FIFO**: entrada crea capa; salida consume capas oldest-first (COGS ponderado);
    `bal.avg_cost` queda en el ponderado de capas abiertas.
- **Reversa:** `reversal.py` NO se tocó. Reusa `post_receive`/`post_issue`, así que crea/
  consume capas por la misma vía y el kardex de costo cuadra con el físico (probado).

## Contrato / invariantes

- La política se fija con `costing.set_cost_policy(company, branch=None, method=...)` (ya
  existía; versiona y audita `INVENTORY_COST_POLICY_SET`). `branch=None` aplica a toda la
  empresa por fallback.
- Invariante FIFO: `Σ StockMovementCostLayer.qty_remaining == StockBalance.qty_on_hand`
  por (company, branch, warehouse, item).
- Las capas SOLO existen bajo FIFO; STANDARD/AVERAGE no las materializan.
- Granularidad FIFO: por (warehouse, item) en orden de recepción (`created_at, id`). El lote
  físico elegido (FEFO/FIFO) es independiente del consumo de capas de costo (flujo de costo
  ≠ flujo físico). *Follow-up posible:* capas por lote si se requiere costo por lote exacto.

## Validación (worktree, contenedor efímero montado)

El contenedor `backend` en ejecución monta el repo principal, no el worktree, y su imagen va
algunas dependencias atrás del baseline. Para validar el worktree se monta su `backend/` en
un contenedor efímero con el entrypoint sobreescrito (evita el `migrate` automático) y se
instala el entorno exacto del contenedor vivo:

```bash
# 1) capturar el entorno del contenedor vivo (sin Django, ya está en la imagen)
docker compose exec -T backend pip freeze | grep -vE '^(pkg[-_]resources|[Dd]jango==)' \
  > <worktree>/backend/_cost_freeze.txt
# 2) correr pytest en el efímero
docker compose run --rm --no-deps --entrypoint bash \
  -v <worktree>/backend:/app/backend backend -lc \
  "pip install -q -r /app/backend/_cost_freeze.txt >/dev/null 2>&1; cd /app/backend && \
   DJANGO_SETTINGS_MODULE=config.settings.test PYTHONPATH=/app/backend/src \
   PYTEST_DB_SLOT=95 PYTEST_DB_BASE_NAME=test_erp_cost \
   python -m pytest -p no:cacheprovider -q --create-db"
```
(`_cost_freeze.txt` es solo andamiaje de validación: borrarlo antes de commitear.)

**Nota sobre el render de PDF (WeasyPrint):** el `pip freeze` instala el *wheel* de
WeasyPrint pero NO sus libs nativas del SO (pango/gobject), así que `nomina/
test_planilla_pdf::test_render_planilla_pdf_real_bytes` puede fallar en este efímero por
`OSError` al renderizar — es **artefacto del harness, no del costeo ni del gate** (el gate
`make qa-ci-ci` hace `docker compose up -d --build`, que reconstruye desde
`backend.Dockerfile.dev` con las libs). Para una suite 100% verde en el efímero, una de dos:
(a) usar una imagen con las libs (`docker compose up -d --build backend` y `exec`, en vez de
`run` sobre imagen vieja), o (b) excluir ese test: `--ignore=src/apps/kernels/nomina/tests/
test_planilla_pdf.py`. (En mainline el test ya salta limpio si faltan las libs: ver el
hardening del guard en `test_planilla_pdf.py`.)

**Estado:** `inventarios/tests` 44/44 verde (5 nuevos de costeo + 39 de regresión del
kernel). `test_costing_fifo.py` (consumo oldest-first, balance = capas, reversa cuadra) y
`test_costing_standard.py` (varianza + valuación a estándar + no-regresión del promedio).
retail_pos: 15/15 corridas verdes en aislamiento (el "flaky" anotado no se reproduce sobre
`31c9b7af`; los `order_by` desempatan por `id` y los scopes de test son únicos).

## Empaquetado
- Catálogo de auditoría: no requiere nuevos `event_type` (la varianza viaja en
  `INVENTORY_MOVEMENT_POSTED` vía `cost_variance` del movimiento + metadata existente).
- Post-merge: `migrate` (aplica `inventarios.0010`). No hay seed nuevo.
- *Follow-up opcional:* API REST para `set_cost_policy` y para editar `standard_cost` por
  ítem (hoy por shell/admin), y endpoint de valuación que sume capas FIFO.
