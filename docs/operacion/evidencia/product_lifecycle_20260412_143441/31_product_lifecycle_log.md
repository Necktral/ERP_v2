# Product Lifecycle Full Cycle Log

- Generated at (UTC): `2026-04-12T20:35:41.827455+00:00`
- Timezone reference: `America/Managua`
- Seed: `20260412`
- Functional status: **FAIL**

## Step Trace

- [IAM] -> Bootstrap status -> sistema fresh=true [[200]] -> PASS | actual: HTTP 200 (http=200)
- [IAM] -> Validar estado fresh -> is_fresh=true -> PASS | actual: is_fresh=True
- [IAM] -> Bootstrap init admin -> admin creado [[201]] -> PASS | actual: HTTP 201 (http=201)
- [IAM] -> Login inicial -> token header emitido [[200]] -> PASS | actual: HTTP 200 (http=200)
- [IAM] -> Bootstrap organización base -> holding/company/branch creados [[200]] -> PASS | actual: HTTP 200 (http=200)
- [IAM] -> Habilitar setup 2FA -> secret TOTP emitido [[200]] -> PASS | actual: HTTP 200 (http=200)
- [IAM] -> Confirmar 2FA -> 2FA activo [[200]] -> PASS | actual: HTTP 200 (http=200)
- [IAM] -> Login con challenge 2FA -> challenge one-time [[202]] -> PASS | actual: HTTP 202 (http=202)
- [IAM] -> Verificar denegación sin segundo factor válido -> acceso denegado [[400]] -> PASS | actual: HTTP 400 (http=400)
  - detail: Código inválido.

## Error

- `No fue posible completar verify 2FA`
