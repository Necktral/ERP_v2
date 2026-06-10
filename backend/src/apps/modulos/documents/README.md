# Módulo `documents` — IDP (Intelligent Document Processing)

Subsistema para **procesar documentos** (facturas, recibos, tickets de combustible, planillas,
generales). El objetivo a futuro es IDP pleno; este módulo entrega la **fase F1** y deja el
andamiaje para las siguientes.

## Pipeline IDP
```
Captura → Clasificación → OCR → Extracción → Validación → Revisión humana → Integración
```
- **F1 (este módulo):** captura + almacenamiento + **OCR (Tesseract)** + **revisión humana**.
- **F2:** extracción estructurada por tipo (PaddleOCR / LayoutLM) → `extracted_fields`.
- **F3:** clasificación automática del `doc_type`.
- **F4:** validación + straight-through (auto-crear/ligar el registro de negocio).

El modelo `ScannedDocument` ya incluye `doc_type`, `extracted_fields` (JSON) y `linked_object_*`
para soportar F2–F4 sin reescritura.

## Modo híbrido (offline-first)
El dispositivo **captura la imagen offline** y, al reconectar, hace `POST` al endpoint de subida
(mismo endpoint para online y para sincronización). El **OCR corre en el servidor** mediante el
command `process_pending_ocr` (no hay runner asíncrono en el repo; se agenda por cron/systemd).

## API (`/api/documents/`)
| Método | Ruta | Permiso | Descripción |
|---|---|---|---|
| GET | `/health/` | — | Healthcheck. |
| POST | `/scans/upload/` | `documents.scan.create` | Sube imagen (`image_base64`, `doc_type`, `content_type?`, `branch_id?`) → crea `PENDING_OCR`. |
| GET | `/scans/` | `documents.scan.read` | Lista por empresa (filtros `status`, `doc_type`). |
| GET | `/scans/<id>/` | `documents.scan.read` | Detalle (texto OCR + campos). |
| POST | `/scans/<id>/review/` | `documents.scan.review` | Revisión humana (`extracted_fields?`, `doc_type?`) → `REVIEWED`. |

Requiere contexto de empresa (`X-Company-Id`). Estados: `PENDING_OCR → PROCESSED → REVIEWED`
(o `FAILED` si el motor falla; el fallo nunca rompe la request, degrada el documento).

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
