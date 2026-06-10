# Handoff a Codex — seed de puestos agrícolas (HR) `feat/hr-positions-seed`

> Escrito por Claude (backend) el 2026-06-10. Claude construye+valida **local**; **Codex hace el
> PR/merge** cuando el acceso a GitHub esté resuelto (el token `gh` cayó a 401 por el cobro Enterprise;
> `git push` sí funciona). Comunicación y UI en español.

## Qué es
Deja sembrado el **catálogo de puestos agrícolas por empresa**, "concatenado" con el seed RBAC pero
**sin mezclar dominios**: RBAC es global (roles/permisos); los puestos (`JobPosition`) son por empresa.
`seed_hr_positions_v01(company)` crea 13 puestos canónicos y los mapea (`PositionRoleMap`) a roles RBAC.
Agrega **1 rol nuevo** `finca_tecnico` (asesor agrónomo) que **reusa permisos `finca.*` ya existentes**:
**no agrega permisos nuevos, NO agrega migración**, no crea empleados ni nómina.

## Rama / orden de merge
- Rama `feat/hr-positions-seed`, **independiente, basada en `master` remoto (`5abd6518`/#73)**.
- **No depende** del stack diagnostics (B-5/CodeUnit/Supervisión) ni de `feat/rbac-predefined-roles`.
  Se puede mergear en **cualquier orden** respecto a esas; sin colisión (distinto módulo, **sin migración**).
- Commit propio toca solo: `hr/seed_positions_v01.py`, `hr/management/commands/seed_hr_positions_v01.py`
  (+ `__init__.py` del package nuevo), `hr/tests/test_seed_positions_v01.py`, y `rbac/seed_v01.py`
  (3 descripciones alineadas + **1 rol nuevo `finca_tecnico`** mapeado a permisos `finca.*` existentes;
  sin permisos nuevos, sin migración).
- **NO incluir** el WIP de frontend del usuario ni los `M` previos de `hr/urls.py`/`hr/views.py`/
  `hr/tests/test_hr.py` (cambios del usuario, fuera de esta tarea).

## Decisiones de diseño (ya tomadas con el usuario)
1. **Multi-cargo:** un empleado puede tener **más de un cargo**. **Ya funciona** sin cambios de esquema:
   `reconcile_employee_roles` ([hr/services.py](../../backend/src/apps/modulos/hr/services.py)) hace la
   **unión** de los roles de **todas** las `EmploymentAssignment` activas. Se agregó un test que lo fija.
2. **Habilitar/deshabilitar:** los 13 puestos nacen **activos**; flags CLI `--disable`/`--enable`/`--only`
   (códigos CSV). En re-corridas el seed **NO pisa** el `is_active` de un puesto que no esté nombrado por
   un flag (respeta el toggle manual del operador).
3. **Ingeniero/Técnico Agrónomo → rol NUEVO `finca_tecnico`** (asesor técnico, distinto del capataz):
   ve todo y **define el plan de labores** (`finca.labor.manage`); **NO** captura ejecución diaria
   (`work.capture`, eso es del capataz) ni postea costos (`cost.post`, del mandador). SoD.
4. **Jerarquía de capataces:** se separan **`Capataz en Jefe`** (capataz mayor) y **`Capataz`** — ambos
   con permisos `finca_capataz`; la diferencia es de puesto/jerarquía (mandador > capataz en jefe > capataces).
5. **Solo comando standalone** — NO se tocó `bootstrap_company`.

## Catálogo (13) — `code | name | rol RBAC | scope`
```
FNC-N1-010 Gerente Agrícola                -> finca_mandador     COMPANY
FNC-N2-010 Administrador de Finca          -> finca_mandador     BRANCH
FNC-N2-020 Mandador                        -> finca_mandador     BRANCH
FNC-N2-025 Capataz en Jefe                 -> finca_capataz      BRANCH
FNC-N2-030 Capataz                         -> finca_capataz      BRANCH
FNC-N3-010 Ingeniero Agrónomo              -> finca_tecnico      BRANCH   (rol NUEVO, asesor)
FNC-N3-020 Encargado de Insumos Agrícolas  -> warehouse_operator BRANCH
FNC-N4-010 Operador de Maquinaria Agrícola -> fleet_driver       BRANCH
FNC-N4-020 Aplicador de Agroquímicos       -> (sin rol)
FNC-N5-010 Trabajador de Campo Permanente  -> (sin rol)
FNC-N5-020 Jornalero (trabajos al día)     -> (sin rol)
FNC-N5-030 Cortador de Café                -> (sin rol)
FNC-N5-040 Ayudante de Campo               -> (sin rol)
```
Los "sin rol" **no otorgan acceso al sistema** por el puesto (regla: jornalero sin acceso por defecto).

## Uso
```
python manage.py seed_hr_positions_v01 --company-code <CODE>
python manage.py seed_hr_positions_v01 --company-code <CODE> --disable FNC-N4-010,FNC-N5-030
python manage.py seed_hr_positions_v01 --company-code <CODE> --only FNC-N2-020 --json
```

## Validación local (sin CI) — todo verde
- `ruff` + `mypy` sobre archivos nuevos + `seed_v01.py`; static-scan CLEAN.
- `makemigrations --check --dry-run hr rbac` → **No changes** (sin esquema).
- `pytest src/apps/modulos/hr/tests` verde (14 nuevos: catálogo de 13, idempotencia, jornalero-sin-rol,
  mapeos, **SoD del rol nuevo finca_tecnico**, enable/disable + respeto de toggle manual, only,
  rol-inexistente=error claro, **multi-cargo**, comando). `pytest src/apps/modulos/rbac/tests
  src/tests/test_onboarding_e2e.py` → 22 verdes (seed sigue
  idempotente tras el tweak de descripciones).
