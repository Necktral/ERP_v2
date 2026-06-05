# Bug Bounty Findings (Local Only)

- Status: **FAIL**
- Evidence dir: `/home/necktral/ERP_CRM/docs/operacion/evidencia/bug_bounty_local_20260320_1207`

## Gate
- gitleaks_clean: PASS
- pip_audit_blocking_clean: PASS
- npm_audit_blocking_clean: FAIL
- manage_check_pass: PASS
- audit_chain_pass: PASS
- security_pytest_pass: PASS
- static_scan_pass: PASS
- dast_pass: PASS

## Blocking Findings
- NPM @quasar/app-vite severity=high fix=True
- NPM flatted severity=high fix=True
- NPM serialize-javascript severity=high fix=True
