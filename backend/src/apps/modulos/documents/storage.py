"""Abstracción de almacenamiento de la imagen del documento.

F1 guarda la imagen como base64 en la propia fila (`storage_backend="db"`). El día que el
volumen lo exija, se agrega aquí un backend "object" (MinIO/S3): subir los bytes y guardar
la clave en `image_ref`, **sin cambiar** el resto del pipeline IDP ni los contratos de API.
"""
from __future__ import annotations

import base64

from .models import ScannedDocument


class UnsupportedStorageBackendError(RuntimeError):
    """El backend de almacenamiento configurado aún no está soportado (p. ej. object storage)."""


def store_image(doc: ScannedDocument, raw_bytes: bytes, content_type: str = "") -> None:
    doc.content_type = content_type or doc.content_type
    doc.byte_size = len(raw_bytes)
    if doc.storage_backend == "db":
        doc.image_data = base64.b64encode(raw_bytes).decode("ascii")
        return
    raise UnsupportedStorageBackendError(  # pragma: no cover - object storage en fase posterior
        f"storage_backend no soportado aún: {doc.storage_backend}"
    )


def load_image_bytes(doc: ScannedDocument) -> bytes:
    if doc.storage_backend == "db":
        if not doc.image_data:
            return b""
        return base64.b64decode(doc.image_data.encode("ascii"))
    raise UnsupportedStorageBackendError(  # pragma: no cover - object storage en fase posterior
        f"storage_backend no soportado aún: {doc.storage_backend}"
    )
