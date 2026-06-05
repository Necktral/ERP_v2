# Bug Bounty Findings (Local Only)

- Generated (UTC): 2026-03-09T06:30:53.880570+00:00
- Overall status: **FAIL**
- Manifest hash: `dfbac9b2d0a988e8ca9ed4533594bef75334e68965a2548cd8c2b9f431e8728c`

## Gate Summary
- `gitleaks_clean`: FAIL
- `pip_audit_blocking_clean`: PASS
- `npm_audit_blocking_clean`: FAIL
- `django_check_pass`: PASS
- `audit_verify_chain_pass`: PASS
- `security_pytest_pass`: FAIL
- `static_scan_pass`: PASS
- `required_evidence_present`: PASS

## Findings
### 1. [CRITICAL] Secretos detectados por gitleaks
- Evidence: `10_gitleaks.json`
- Count: 72
- Owner: Security/DevOps
- Action: Rotar secretos comprometidos, eliminar secretos del repo y reforzar políticas de pre-commit/CI.

### 2. [HIGH] Dependencias Node HIGH/CRITICAL con fix disponible
- Evidence: `12_npm_audit.json`
- Count: 5
- Owner: Frontend Platform
- Action: Aplicar npm audit fix controlado y validar build/tests.

### 3. [MEDIUM] Suite de tests de seguridad mínima con fallos
- Evidence: `22_security_pytest.txt`
- Count: 1
- Owner: Backend QA/Security
- Action: Corregir test(s) fallidos y estabilizar comportamiento esperado de 2FA/seguridad.

### 4. [LOW] Hallazgos Trivy (advisory no-blocking en esta corrida)
- Evidence: `13_trivy_fs.json`
- Count: 2
- Owner: Security/DevOps
- Action: Revisar y priorizar remediación de vulnerabilidades/misconfiguraciones reportadas por Trivy.

## Blocking Criteria Applied
- gitleaks must be clean (0 findings).
- pip-audit: no HIGH/CRITICAL with fix available.
- npm audit: no HIGH/CRITICAL with fix available.
- manage.py check, audit_verify_chain, and security pytest must pass.
