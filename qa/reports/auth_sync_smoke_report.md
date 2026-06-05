# Auth/Sync Smoke Report

- Timestamp: `2026-03-22T00:50:14.801851Z`
- Overall: **PASS**
- Context: company=2 branch=3

| Check | Result | HTTP | Reason | Request ID |
|---|---|---:|---|---|
| login | PASS | 200 |  | f36cdf0221104bc2957620664fbe574b |
| challenge_without_csrf | PASS | 403 | AUTH_CSRF_FAILED | 991c790dde36411abfd52fd3a7a751d6 |
| challenge_with_csrf | PASS | 201 |  | 7781f90368b241a1acf138f563c7b5eb |
| enroll | PASS | 201 |  | 85d554df295d4801b10bf58b1be67c95 |
| batch_signed_demo_ping | PASS | 200 | applied=1 | d6b39157d0354a3ab1d03a9259653ef8 |
| revoke | PASS | 200 | REVOKED | 3765bd1ac0a84a09829f19541615bf24 |
| jwt_insecure_warning_absent | PASS | 0 | warning_count=0 |  |
