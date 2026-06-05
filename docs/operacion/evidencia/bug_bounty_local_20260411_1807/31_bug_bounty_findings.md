# Bug Bounty Findings (Local Only)

- Status: **FAIL**
- Evidence dir: `/home/necktral/ERP_CRM/docs/operacion/evidencia/bug_bounty_local_20260411_1807`

## Gate
- gitleaks_clean: FAIL
- pip_audit_blocking_clean: PASS
- npm_audit_blocking_clean: FAIL
- manage_check_pass: PASS
- audit_chain_pass: FAIL
- security_pytest_pass: FAIL

## Blocking Findings
- NPM axios severity=critical fix=True
- NPM lodash severity=high fix=True
- NPM path-to-regexp severity=high fix=True
- NPM picomatch severity=high fix=True
- NPM vite severity=high fix=True
