# Módulo `documents` — IDP (Intelligent Document Processing)

Subsistema para **procesar documentos** (facturas, recibos, tickets de combustible, planillas,
generales). El objetivo a futuro es IDP pleno; este módulo entrega la **fase F1** y deja el
andamiaje para las siguientes.

## Pipeline IDP
```
Captura → Clasificación → OCR → Extracción → Validación → Revisión humana → Integración
```
- **F1:** captura + almacenamiento + **OCR (Tesseract)** + **revisión humana**.
- **F2 (CONSTRUIDA, determinista):** extracción de campos (`extraction.py`) — regex/heurísticas
  nicaragüenses (RUC/cédula, fecha, total vs subtotal, número de documento, placa, galones), cada
  campo con `confidence` (`high` con etiqueta explícita) + línea de `evidence` + `needs_review`.
  El batch encadena OCR→extracción; estado nuevo **`EXTRACTED`** = borrador en cola de revisión
  (`GET /scans/?status=EXTRACTED`). Sugerencia de `doc_type` por keywords (solo sugiere).
  **Invariante:** la extracción JAMÁS toca `linked_object_*` ni crea objetos de negocio.
  Punto de enchufe IA: `run_extraction()` — un extractor LLM (estructurado, detrás del kill
  switch `ai_features_enabled()`) podrá sumarse sin cambiar el contrato.
- **F3:** clasificación automática del `doc_type` (hoy: sugerencia por keywords en F2).
- **F4:** validación + straight-through (auto-crear/ligar el registro de negocio).

## Modo híbrido (offline-first) — los DOS canales de entrada
1. **App de remisiones / cámara (campo, móvil):** captura la **imagen offline** y, al reconectar,
   hace `POST` al endpoint de subida (mismo endpoint para online y para sincronización).
2. **PC con documentos escaneados (oficina):** sube el **PDF del escáner** al mismo endpoint;
   `ocr.py` detecta `%PDF`, renderiza las páginas con **pypdfium2** (tope 5 págs, wheel pura sin
   binarios de sistema) y OCRea cada una. PDF corrupto → `FAILED` (degrada, nunca rompe).

El **OCR corre en el servidor** mediante el command `process_pending_ocr` (no hay runner
asíncrono en el repo; se agenda por cron/systemd), que encadena la extracción F2.

## API (`/api/documents/`)
| Método | Ruta | Permiso | Descripción |
|---|---|---|---|
| GET | `/health/` | — | Healthcheck. |
| POST | `/scans/upload/` | `documents.scan.create` | Sube imagen (`image_base64`, `doc_type`, `content_type?`, `branch_id?`) → crea `PENDING_OCR`. |
| GET | `/scans/` | `documents.scan.read` | Lista por empresa (filtros `status`, `doc_type`). |
| GET | `/scans/<id>/` | `documents.scan.read` | Detalle (texto OCR + campos). |
| POST | `/scans/<id>/extract/` | `documents.scan.review` | Etapa F2 manual (re-extraer / rezagados `PROCESSED`) → `EXTRACTED`. |
| POST | `/scans/<id>/review/` | `documents.scan.review` | Revisión humana (`extracted_fields?`, `doc_type?`) → `REVIEWED`. |

Requiere contexto de empresa (`X-Company-Id`). Estados: `PENDING_OCR → PROCESSED → EXTRACTED → REVIEWED`
(o `FAILED` si el motor OCR falla; el fallo nunca rompe la request, degrada el documento).

## OCR y almacenamiento
- **Motor:** Tesseract (open-source), binario `tesseract-ocr` + `tesseract-ocr-spa` en el Docker
  (`docker/backend.Dockerfile.*`). Imports lazy en `ocr.py` (degradan a `FAILED` si falta el binario).
- **Almacenamiento:** F1 guarda la imagen en la DB (base64) detrás de `storage.py`; cambiar a object
  storage (MinIO) es un branch en `store_image`/`load_image_bytes`, sin tocar el resto.

## Comando
```
python manage.py process_pending_ocr --limit 50
```
Procesa los documentos `PENDING_OCR` (etapa OCR del pipeline).
