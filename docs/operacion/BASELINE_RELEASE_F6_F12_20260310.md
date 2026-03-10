# Baseline Release F6-F12 (Staging PASS)

Fecha: 2026-03-10  
Branch release: `release/f6-f12-staging-pass-20260310`  
Base commit al crear rama: `5d63121`

## Objetivo de publicación

Publicar backend y documentación de F6-F12 en flujo branch + PR, manteniendo:

- cambios aditivos (sin breaking changes);
- evidencia masiva fuera del versionado GitHub;
- trazabilidad de validaciones de seguridad y pruebas.

## Checklist de baseline

- [x] Rama de release creada.
- [x] Política de evidencia masiva definida en `.gitignore`.
- [x] Documento de estado ejecutivo separado de blueprint.
- [x] Pre-push de seguridad ejecutado (`gitleaks`, `pip-audit`, `npm audit`).
- [x] Validación técnica ejecutada (`manage.py check`, `pytest -q login_module/src`).
- [ ] Push de rama a `origin`.
- [ ] PR creado con título de release y checklist de aceptación.

## Resultado de validaciones (2026-03-10)

- `python manage.py check`: PASS
- `pytest -q login_module/src`: PASS
- `npm run lint/typecheck/test/build`: PASS
- `pip-audit` (`requirements/base.txt`, `requirements/prod.txt`): PASS (sin vulnerabilidades)
- `gitleaks` con `.gitleaks.toml`: FAIL (`48` hallazgos reportados en `qa_gitleaks.json`)
- `npm audit --json`: WARN/BLOCKER (`2` high sin fix disponible: `@quasar/app-vite`, `serialize-javascript`)
