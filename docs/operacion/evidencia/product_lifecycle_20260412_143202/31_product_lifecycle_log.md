# Product Lifecycle Full Cycle Log

- Generated at (UTC): `2026-04-12T20:32:51.695897+00:00`
- Timezone reference: `America/Managua`
- Seed: `20260412`
- Functional status: **FAIL**

## Step Trace

- [IAM] -> Bootstrap status -> sistema fresh=true [[200]] -> PASS | actual: HTTP 200 (http=200)
- [IAM] -> Validar estado fresh -> is_fresh=true -> PASS | actual: is_fresh=True
- [IAM] -> Bootstrap init admin -> admin creado [[201]] -> PASS | actual: HTTP 201 (http=201)
- [IAM] -> Login inicial -> token header emitido [[200]] -> PASS | actual: HTTP 200 (http=200)

## Error

- `Login inicial sin access/refresh`
