# Nomina Field Attendance Capture (PR17)

## Context

PR17 adds the backend capture layer for field attendance on top of the existing Nomina attendance foundation.

## Scope

- Add field capture models for crews, crew work days, crew reports, and worker events.
- Support idempotent capture by crew and date.
- Support eventual workers by cedula when no HR employee exists yet.
- Record audited worker transfers between crews.
- Use maker/checker approval for field reports and block self-approval through IAM approvals.
- Build approved `AttendanceReport` rows from approved field reports.
- Seed required `nomina.field.*` and attendance permissions.

## Blast Radius

- Domains touched: `kernels.nomina`, `modulos.audit`, `modulos.rbac`.
- Layer mix includes runtime backend plus migration.
- The PR is classified as high risk by the blast radius guard because it adds runtime behavior and a migration.

## Controls

- Keep the change backend-only and limited to Nomina field capture, audit contracts, RBAC seed, migration safety metadata, and this design note.
- Do not write directly to `PayrollEntry`.
- Keep approval state in IAM approvals and materialize payroll-facing attendance only through `AttendanceReport`.
- Keep endpoint compatibility scoped to `/api/nomina/field/*` routes already owned by Nomina.

## Validation

- `python manage.py check`
- `python manage.py makemigrations --check --dry-run --noinput`
- `ruff check src/apps/kernels/nomina/ src/apps/modulos/audit/contracts.py src/apps/modulos/rbac/seed_v01.py`
- `pytest src/apps/kernels/nomina/tests/test_field_attendance.py src/apps/kernels/nomina/tests/test_nomina_services.py src/apps/modulos/rbac/tests/test_rbac.py src/tests/test_contract_guards.py -q`
- `make qa-migration-safety-guard`
- `make qa-coverage-by-domain-guard`
- `make qa-run-profile PROFILE=pr`

## Rollback

- Prefer roll-forward fixes for shared environments after migration application.
- Before shared application, revert the PR branch and remove `nomina.0010_field_capture_models` with the associated migration safety metadata.
