# Orientaciones para Codex — sesión 2026-06-11

**Quién hizo qué:** Claude trabajó SOLO en local (construir, arreglar, validar en Docker,
simular, probar). **Codex** hace todo lo de git/GitHub: ramas, commits, PRs, merge. Este
documento es el paquete ejecutable. No hay nada commiteado por Claude.

**Modo vigente:** Claude no toca git; Codex sí. Commits por ruta EXPLÍCITA (nunca `git add .`).
Footer de commit `Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>`. Comunicación y UI
en español. Tests detectan bugs: si uno falla, arreglar el código, no ablandar el test.

---

## 1. Estado del árbol (sin commitear)

Es un cambio grande: la **vertical RH + Asistencia + Nómina** del backend, su **frontend
multi-empresa** reconstruido (Ola 0), y APIs nuevas de **parties / compras / comisariato / org / rbac**.

- **Backend nuevo:** `kernels/nomina/{asistencia_dia,views_asistencia,biometric/,contract_templates…}`,
  `modulos/hr/{photo_service,contract_templates}`, `modulos/parties/{serializers,urls,views,tests}`,
  migraciones `hr/0006–0009` y `nomina/0013`.
- **Backend modificado:** `kernels/nomina/{models,serializers,services,urls,views}`,
  `modulos/{hr,audit,rbac,comisariato,compras,org,sync_engine}/…`, `config/urls.py`, `rbac/seed_v01.py`.
- **Frontend:** reconstrucción casi total (login glass, AppLayout con selector multi-empresa,
  páginas de hr/nomina/asistencia/devices/org/admin/parties/caja/cartera/compras/facturación/inventario,
  features/* y core/*). Muchos archivos viejos BORRADOS (MainLayout, *Page.vue legacy, services/*).

### Excluir del commit (NO va al repo)
- `simulacion/` — artefactos de prueba de Claude (ver §6); decisión del dueño si se conservan.
- `excel/` y cualquier `*:Zone.Identifier`.
- `qa/reports/*` (bandit.json, migration_safety_guard.json) — son salidas de gate, no fuente.
- `.vscode/settings.json` — preferencia local (confirmar con el dueño).

---

## 2. Qué validó Claude (verde) vs qué NO

**VALIDADO en Docker (suite completa con `--create-db`, slot limpio) — verde:**
- `hr/`, `kernels/nomina/` (incl. biometric, asistencia_dia), `audit/`, `sync_engine/`,
  `rbac/seed_v01` + `test_seed_roles`. Suite backend COMPLETA pasó (único rojo previo era el
  contrato `/enrolar`, ya corregido — ver §3).
- `qa-frontend-ci` completo (npm ci → lint → typecheck → tests → build): verde.
- mypy del CI (config raíz, 742 archivos): `Success`. ruff: limpio. static-scan: limpio en
  TODO el WIP. makemigrations --check: sin cambios. Guards de migración y arquitectura: verdes.

**NO validado por Claude (atención de Codex — apareció como WIP del dueño después):**
- `modulos/parties/` (serializers/urls/views/tests nuevos), `modulos/compras/` (urls/views/tests),
  `modulos/comisariato/` (urls/views/tests), `modulos/org/module_catalog.py`, `modulos/rbac/{urls,views}`.
- Frontend nuevo masivo de **caja, cartera, compras, facturación, inventario, parties, org, admin**
  (las páginas de hr/nomina/asistencia/devices SÍ se recorrieron en navegador — ver §5).
- Acción Codex: correr la suite COMPLETA + `qa-frontend-ci` una vez más sobre el árbol entero
  antes del PR; revisar que parties/compras/comisariato no agreguen **edges de arquitectura** ni
  **rutas** sin registrar (a Claude no le rompieron los gates locales, pero no se aislaron).

---

## 3. Correcciones que Claude YA aplicó (no rehacer)

1. **Contrato `/enrolar`** — `backend/src/tests/test_sync_device_enrollment_flow.py`: el assert
   esperaba `/device/enroll`; se actualizó a `/enrolar` (el WIP cambió la ruta del front; el test
   estaba desactualizado, no el código).
2. **11 errores de mypy** (estrechamiento de tipos, sin cambio de comportamiento):
   - `hr/services.py`: `linked_user`/`contract.position`/`period_labels` (None-narrowing + anotación).
   - `hr/photo_service.py`: `img: Image.Image`.
   - `kernels/nomina/services.py:~1002`: guard `if check.employee_id is None: continue`.
   - `kernels/nomina/biometric/services_biometric.py`: `match_cache: dict[str, Employee | None]`
     + `match_employee(...) -> Employee | None`.
3. **E741 ruff** — `hr/views.py:771`: `l` → `value, label` en `_choices`.
4. **Gates de baseline** (ya escritos en los JSON, listos para commitear):
   - `qa/contracts/migration_safety_baseline.json`: registradas hr/0006–0009 + nomina/0013
     (sha256, risk_class, rollout/rollback, owner, ticket_ref). **Verificado: guard verde.**
   - `qa/contracts/architecture_dependency_baseline.json`: edges `modulos.hr->modulos.org` y
     `modulos.audit->modulos.sync_engine` agregados. **Guard verde.** (Nota: el guard avisa
     "1 baseline edge ya no presente" — oportunidad de poda, no bloquea.)
5. **Frontend** — pantallas que el revamp borró pero el router seguía esperando:
   `pages/SelectContextPage.vue` y `pages/ForbiddenPage.vue` (recreadas, estilo glass con tokens
   `--app-*`), rutas `/select-context` y `/403` en `router/routes.ts`, y el chip de empresa del
   topbar como selector multi-empresa (`layouts/AppLayout.vue`). **El dueño expandió esto** (menú
   desplegable, páginas Organización/Usuarios) — tomar la versión en disco tal cual.

---

## 4. Procedimiento de commit sugerido (para Codex)

Rama desde `master` (`00b65536`), p. ej. `feat/hr-asistencia-nomina-multiempresa`.
Dado el tamaño, considerar **2 PRs** si CI lo pide, pero el árbol es coherente como uno solo:

- **PR backend+gates:** todo `backend/src/apps/{kernels/nomina,modulos/hr,modulos/audit,modulos/rbac,
  modulos/parties,modulos/compras,modulos/comisariato,modulos/org,modulos/sync_engine}`, `config/urls.py`,
  `backend/src/tests/test_sync_device_enrollment_flow.py`, ambos `qa/contracts/*baseline.json`.
- **PR frontend:** todo `frontend/` (incluye borrados del revamp, `package-lock.json`, páginas/features/core/router/layouts nuevos). Excluir `frontend/dist/` y `frontend/node_modules/`.

CI debería salir verde a la primera en la parte que Claude validó. Si rompe en parties/compras/
comisariato/org, son módulos sin aislar (§2) — revisar ahí primero.

---

## 5. Hallazgos de FRONTEND (verificados en navegador con datos reales)

Recorrido Playwright real contra el front en `:3000` con los datos de simulación. Consola y red
**limpias** en todo el flujo de hr/nomina/asistencia. Hallazgos (prioridad ALTA→BAJA):

1. **[RESUELTO por Claude+dueño]** `/403` y `/select-context` inexistentes → el guard redirigía a
   rutas que daban "404 Oops". Repuestas. Verificar que la versión final del dueño compile y que el
   login multi-empresa caiga en el selector (probado: funciona).
2. **[MEDIA] Home post-login fijo** — `router/routes.ts`: `redirect: '/recursos-humanos'` (desktop)
   sin mirar permisos. Un usuario de campo (solo `nomina.field.read`) aterriza en `/403` como
   bienvenida. Debería elegir el primer módulo permitido (p. ej. caer a `/asistencia`).
3. **[BAJA] Lista de períodos muestra Neto C$ 0.00** en borrador con planillas ya calculadas: los
   totales del período solo se rolean al aprobar (`kernels/nomina/accounting_link.py:70`). Es por
   diseño, pero confunde; la lista podría sumar las sheets en vivo.

---

## 6. Hallazgos de KERNEL NÓMINA (revelados por la simulación de planilla real)

Comparando las planillas generadas contra el excel real de abril 2026. **Decisiones de negocio +
1 corrección legal** — confirmar con el dueño antes de tocar:

1. **[ALTA — corrección legal] La base del IR no resta el INSS laboral.**
   `kernels/nomina/models.py:~756` (`compute_all`) anualiza sobre `basic_earned` (bruto). Por Ley 822
   la renta neta del trabajo = bruto − INSS laboral. Efecto medido: a un BODEGUERO de 12.000 le
   retuvo IR 155.00; con la base correcta (bruto − 7%) sería ~100. Arreglo: `period_income =
   basic_earned − inss_laboral` en la llamada a `IRBracket.calculate_period_ir`.
2. **[MEDIA — decisión de negocio] El kernel retiene IR a los SIN INSS** (legalmente correcto), pero
   la planilla real del dueño los lleva con retenciones en 0. Definir: ¿elección por período como el
   INSS, o se acepta el comportamiento del kernel?
3. **[MEDIA — decisión de negocio] Prestaciones provisionadas vs pagadas.** El kernel provisiona
   vacaciones+13vo como costo patronal (no las paga en el neto); la hoja SIN INSS real las paga
   embebidas cada quincena. Confirmar el tratamiento deseado por tipo de planilla.

---

## 7. Hallazgos de MUNDO A / MUNDO B (pruebas adversariales fuertes)

55 pruebas adversariales (no las suites del CI) en `simulacion/stress/{stress_a,stress_b}.py`,
todas verdes. Ambos mundos resultaron **sólidos** (dedupe concurrente sin lost-update, redacción de
secretos, kill switch hard-env, triage sticky vs sentinel, gate C1, RAG inmune a inyección SQL y de
prompt, CEC explainer solo-lectura, IDP determinista que no integra). **2 mejoras de robustez:**

1. **[BAJA] `record_error_event` no es defensivo de tipos** — `modulos/diagnostics/services.py:39`:
   `(getattr(request, "method", "") or "")[:16]` revienta con `TypeError` si `method` llega como
   `int`. La invariante externa SE SOSTIENE (el handler de señal es best-effort y lo traga), así que
   es fragilidad teórica. Arreglo: `str(getattr(...) or "")[:16]` (igual para `path`/`request_id`).
2. **[BAJA] El chunker del RAG no parte un párrafo monolítico** — `modulos/knowledge/ingest.py:42`
   (`_split_long`): corta por párrafos (`\n\n`); un párrafo único de >4000 chars sin saltos dobles
   queda en un chunk grande. Con párrafos normales respeta el tope. Arreglo: corte por palabra como
   respaldo cuando un párrafo solo excede `_MAX_CHUNK_CHARS`.

---

## 8. Artefactos de simulación (en `simulacion/`, decisión del dueño si se conservan)

- `simulacion/planilla/planilla_sim.py` — siembra el HOLDING completo (4 empresas con RUC propio:
  agrícola, comisariato, beneficio seco, acopio; 23 trabajadores espejo anónimo del excel real),
  asistencia aleatoria por el canal real (mandador → consolidación → aprobación SoD), planillas
  CON/SIN INSS, cálculo y export xlsx. Idempotente. `--seed 42 --reset` reproduce idéntico;
  `--grant-user <usuario>` da company_admin en las 4 empresas (ya aplicado a `Wis`).
- `simulacion/planilla/salida/*.xlsx` — 8 planillas generadas (CON/SIN INSS por empresa).
- `simulacion/stress/{stress_a,stress_b}.py` — las 55 pruebas adversariales (§7). Útiles como
  regresión de invariantes si se decide promoverlas a `backend/src/.../tests/`.

**Datos dev:** las 4 empresas SIM viven en la DB de desarrollo (company_id 10/12/14/16). El usuario
`Wis` tiene acceso a todas. No tocan producción ni el repo.
