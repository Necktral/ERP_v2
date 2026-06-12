# Orientaciones para Codex — sesión 2026-06-12 (módulo financiamiento ex-SIFA)

**Quién hizo qué:** Claude trabajó SOLO en local (construir, validar en Docker, simular).
**Codex** hace todo lo de git/GitHub: ramas, commits, PRs, merge. Nada de esto está commiteado.

**Modo vigente:** commits por ruta EXPLÍCITA (nunca `git add .`). Footer
`Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>`. Comunicación y UI en español.
Tests detectan bugs: si uno falla, arreglar el código, no ablandar el test.

---

## 1. Paquete principal: módulo FINANCIAMIENTO (listo para PR, verde)

Vertical nuevo que reemplaza el SIFA-ACOPIO VB6 (préstamos a productores de café con doble
saldo C$/US$ + acopio en custodia + fijación de precio + liquidación). Decisiones del dueño:
flujo completo F1+F2; café EN CUSTODIA hasta fijar precio; doble saldo fiel al SIFA.

**Rama sugerida:** `feat/financiamiento-acopio-sifa` (sobre la rama actual
`feat/hr-asistencia-nomina-multiempresa` o sobre main después de que aterrice el wave — ver §3).

**Commit (rutas explícitas, TODAS estas y solo estas):**

```
backend/src/apps/modulos/financiamiento/                  # módulo completo (nuevo)
backend/src/apps/modulos/audit/contracts.py               # +bloque FINANCING_* (event types)
backend/src/apps/modulos/diagnostics/domain_map.py        # +"financiamiento" en _C1_DOMAINS
backend/src/apps/modulos/org/module_catalog.py            # +ModuleSpec("financiamiento", VERTICAL)
backend/src/apps/modulos/rbac/seed_v01.py                 # +16 permisos financing.* + 3 roles + loop company_admin
backend/src/config/settings/base.py                       # +1 línea INSTALLED_APPS (FinanciamientoConfig)
backend/src/config/urls.py                                # +1 línea path api/financiamiento/
backend/pytest.ini                                        # +src/apps/modulos/financiamiento/tests en testpaths
docs/operacion/ORIENTACIONES_FRONTEND.md                  # +§8 (contrato de pantallas del vertical)
docs/operacion/ORIENTACIONES_CODEX_2026-06-12.md          # este documento
```

OJO: a la fecha, el `git diff` de los 7 archivos compartidos contiene EXCLUSIVAMENTE los
hunks de financiamiento (el wave de hoy ya fue absorbido en `7b421ab7`). Si otra sesión
vuelve a tocar esos archivos antes de commitear, separar por hunk (`git add -p`): los de
financiamiento se reconocen por las palabras `financiamiento`/`financing`/`FINANCING_`.

**Mensaje sugerido:**
`feat(financiamiento): vertical ex-SIFA — préstamos a productores (doble saldo C$/US$) + acopio en custodia, fijación y liquidación`

**Validación que Claude ya corrió (verde) y Codex debe repetir antes del PR:**

```bash
# Módulo (11 tests, incluye E2E del ciclo SIFA completo)
docker compose exec -T backend bash -lc "cd /app/backend && \
  DJANGO_SETTINGS_MODULE=config.settings.test PYTHONPATH=/app/backend/src \
  PYTEST_DB_SLOT=96 PYTEST_DB_BASE_NAME=test_erp_db \
  python -m pytest src/apps/modulos/financiamiento/tests/ -p no:cacheprovider -q --create-db"

# Centinelas que el módulo nuevo obliga: domain_map, rbac, org, audit, guard de vistas
docker compose exec -T backend bash -lc "cd /app/backend && \
  DJANGO_SETTINGS_MODULE=config.settings.test PYTHONPATH=/app/backend/src \
  PYTEST_DB_SLOT=96 PYTEST_DB_BASE_NAME=test_erp_db \
  python -m pytest src/apps/modulos/diagnostics/tests/test_domain_calibration.py \
    src/apps/modulos/rbac/tests/ src/apps/modulos/org/tests/ src/apps/modulos/audit/tests/ \
    src/tests/test_contract_guards.py -p no:cacheprovider -q"

# Suite completa (Claude la corrió 2 veces: verde, exit 0)
... python -m pytest -p no:cacheprovider -q
```

La migración `financiamiento/0001_initial.py` ya está generada y aplicada en la DB dev.

**Arquitectura (para el cuerpo del PR):** módulo vertical opt-in (CompanyModule), NO kernel.
Orquesta sin duplicar: doble saldo = `FinancingLoan` envuelve 1-2 `portfolio.Credit` (uno por
moneda; comisión→`fee_amount`, moratorio→`late_payment_penalty_rate`, devengo del kernel
funciona directo); custodia = `inventarios.post_receive` a costo 0; liquidación = abono
`COFFEE_QUOTA` + excedente como `portfolio.Payable` + traslado a bodega propia con costo de
compra; SoD creador≠aprobador≠desembolsador. Tasa C$/US$ por fecha en `ExchangeRate` del módulo.

**Lección de kernel documentada (NO "arreglar" en este PR):**
`portfolio.allocate_payment_to_obligation` compara `allocated > intent.amount` SIN considerar
moneda; para cruces, el módulo crea el intent YA CONVERTIDO en la moneda de la obligación
(tender original en `external_ref`, tasa en la allocation). Si algún día se quiere allocation
cross-currency nativa, es cambio de kernel aparte.

---

## 2. Ya commiteado (no requiere acción): fix proveedor LLM B-5

El fix de `diagnostics/providers.py` (MAX_TOKENS configurable default 4096, parser robusto a
markdown/multilínea, `<think>` sin cerrar ⇒ degrada al heurístico) + setting
`DIAGNOSTICS_LLM_MAX_TOKENS` + 3 tests nuevos **ya viven en `7b421ab7`** (absorbidos por el
amend del wave). Su herramienta de prueba en vivo quedó en `simulacion/stress/sim_ia_local_b5.py`
(untracked — ver §3): pipeline B-5 completo contra OpenThinker3-7B real, 5/5 verde.
Arranque del modelo: `bash /mnt/d/rnfe_models/tools/run_llama_server_b5.sh` (fuera del repo).

---

## 3. Resto del árbol (NO es del paquete financiamiento)

- **Ola A en curso** (facturacion/inventarios/comisariato/portfolio/frontend caja-cartera-ventas,
  migraciones inventarios 0010/0011, comisariato 0003, tests billing/pricing): pertenece a la
  sesión de completitud Ola A; se empaqueta con SUS orientaciones, no con estas.
- **`simulacion/stress/`** (stress_a, stress_b, sim_ia_local_b5): si el dueño decide subirlas,
  ATENCIÓN: `stress_a.py::test_rag_chunk_parrafo_monolitico_no_se_parte_HALLAZGO` está ROJO
  contra el árbol actual — documentaba una limitación que ya se corrigió (`_split_oversized_paragraph`
  en knowledge/ingest.py). Hay que VOLTEAR ese test (asertar que ningún chunk supera el tope)
  antes de subirlo; no es ablandar, es que el hallazgo se resolvió.
- **Excluir del repo:** `excel/`, `programa viejo de finciamiento/` (binario VB6 de 15MB — es
  la referencia histórica del SIFA; guardarlo fuera del repo o en un release/asset, decisión
  del dueño), `*:Zone.Identifier`, `.vscode/settings.json` (preferencia local).

---

## 4. Después del merge

- `python manage.py migrate financiamiento` + `python manage.py seed_rbac_v01` (idempotente)
  en cualquier entorno que se actualice.
- El módulo nace `default_enabled=False`: cada empresa lo enciende por CompanyModule
  (pantalla Organización → Módulos). Sin eso no aparece en NAV ni autoriza nada.
- Frontend: construir las 8 pantallas según `ORIENTACIONES_FRONTEND.md §8` (contrato completo
  de endpoints, permisos por pantalla, códigos `FIN_*` y SoD que la UI debe reflejar).
