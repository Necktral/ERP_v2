# Auditoría IA (PRs a master)

Este repositorio ejecuta una revisión de IA **no bloqueante** en cada Pull Request hacia `master`.
La IA publica **comentarios con severidad** para apoyar la auditoría técnica.

## Requisitos

- Configurar el secreto de GitHub Actions: **OPENAI_API_KEY**.
- (Opcional) Configurar la variable de Actions: **AI_REVIEW_MODEL**.
  - Valor por defecto: `gpt-4o-mini`.

## Alcance

- Se analiza el _diff_ del PR (puede truncarse si es muy grande).
- La IA **no bloquea** merges automáticamente.
- El reporte incluye severidad: `CRITICAL`, `HIGH`, `MEDIUM`, `LOW`.
- Se ejecuta un **escaneo de seguridad full-stack no bloqueante**.

## Dónde se ejecuta

- Workflow: `.github/workflows/ai-review.yml`.
- Evento: `pull_request` hacia la rama `master`.

## Escaneo de seguridad (no bloqueante)

Se ejecutan verificaciones adicionales con salida en el resumen del job y en artefactos:

- **Backend**: `pip-audit` sobre `requirements/base.txt` y `requirements/dev.txt`.
- **Frontend**: `npm audit` en `frontend/`.
- **Repositorio**: `trivy fs` sobre el filesystem completo.

Estos pasos **no bloquean** el merge; son informativos y requieren revisión manual ante hallazgos.

## Herramientas de Auditoría Activa

Además de la revisión estática, el repositorio incluye herramientas de **auditoría dinámica** de seguridad:

- **Simulación de Carga/Ataque (k6)**:
  - Ubicación: `simulacion/auth_load_simulation_extended.js`.
  - Vectores probados: Replay Attacks en 2FA, Idempotencia de Logout, Validaciones de Tokens.
  - Ejecución: `./simulacion/run_simulation.sh`.

## Security CI (blocking)

Existe un workflow separado que **si bloquea** merges cuando hay vulnerabilidades altas/criticas con fix disponible:

- `.github/workflows/security-ci.yml`

## Recomendación operativa

- Si hay hallazgos `CRITICAL` o `HIGH`, revisa manualmente antes de merge.
- Usa la IA como complemento, no como reemplazo de revisión humana.
