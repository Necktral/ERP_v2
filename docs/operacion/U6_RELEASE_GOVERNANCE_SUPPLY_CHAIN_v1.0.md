# U6 RELEASE GOVERNANCE + SUPPLY CHAIN v1.0

## Objetivo

Operar `master` con controles de release y supply chain auditables y bloqueantes, sin cambios funcionales de negocio.

## Contratos U6

- `qa/contracts/github_required_checks.json`: source of truth de checks requeridos.
- `qa/contracts/security_exceptions.json`: excepciones de seguridad con expiración.
- `qa/contracts/github_master_ruleset.json`: política objetivo para branch `master`.

## Gates bloqueantes (CI)

Gate 1 debe pasar con:

- `qa-action-pin-guard` (actions pin SHA).
- `qa-github-required-checks-guard` (checks requeridos válidos).
- `qa-runner-hygiene-guard` (sin residuos críticos del runner).
- `qa-validate-security-exceptions` (excepciones vigentes).
- `qa-security-findings-enforce` (hallazgos `pip`/`npm` contra excepciones).

## Supply chain

Workflow: `.github/workflows/supply-chain-ci.yml`.

Artefactos mínimos:

- `qa_sbom_backend.json`
- `qa_sbom_frontend.json`
- `qa_pip_audit_u6.json`
- `qa_npm_audit_u6.json`
- `qa_security_findings_guard_u6.json`
- `qa_supply_chain_artifacts.sha256`

Política operacional:

- Estos artefactos son **source of truth del workflow `supply-chain-ci`**.
- El consolidado local (`release_evidence_u6.json`) los clasifica como `CI-only` para evitar falso rojo fuera de CI.
- En CI, siguen siendo obligatorios.

## Aplicar/verificar política de master (GitHub API)

Verificar:

```bash
python3 qa/manage_github_ruleset.py --root . --contract qa/contracts/github_master_ruleset.json --mode verify --output qa/reports/github_master_ruleset_verify.json
```

Aplicar:

```bash
python3 qa/manage_github_ruleset.py --root . --contract qa/contracts/github_master_ruleset.json --mode apply --output qa/reports/github_master_ruleset_apply.json
```

Requisitos:

- `gh auth login` activo con permisos de administración del repo.

## Evidencia de release U6

Generar consolidado:

```bash
make qa-export-u6-release-evidence QA_REPORTS_DIR=qa/reports
```

Salida:

- `qa/reports/release_evidence_u6.json`

## Rollback operativo

1. Restaurar `github_master_ruleset.json` a versión previa aprobada.
2. Reaplicar política con `--mode apply`.
3. Re-ejecutar `--mode verify`.
4. Adjuntar `release_evidence_u6.json` en PR de rollback.
