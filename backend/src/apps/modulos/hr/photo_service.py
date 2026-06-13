"""Foto del trabajador — normalización y guardado.

La imagen que sube el usuario (cámara del cel o archivo) se normaliza SIEMPRE:
RGB, máximo 512px por lado, JPEG calidad 85. Así toda foto pesa ~30-80 KB sin
importar la cámara, y el expediente sigue siendo liviano para respaldos/sync.

Pillow se importa perezoso (mismo criterio que el OCR de documents): está en
requirements/base.txt, pero el import vive dentro de la función para que el
módulo cargue aun si la lib del sistema faltara.
"""
from __future__ import annotations

import base64
import io

from django.core.exceptions import ValidationError

from apps.modulos.audit.writer import write_event

from .models import Employee, EmployeePhoto

MAX_UPLOAD_BYTES = 8 * 1024 * 1024  # foto de cámara moderna sin recortar
MAX_SIDE_PX = 512
JPEG_QUALITY = 85


def normalize_photo(raw: bytes) -> tuple[bytes, int, int]:
    """Devuelve (jpeg_bytes, width, height) de la imagen normalizada."""
    from PIL import Image, UnidentifiedImageError  # import perezoso

    try:
        img: Image.Image = Image.open(io.BytesIO(raw))
        img.load()
    except (UnidentifiedImageError, OSError) as exc:
        raise ValidationError({"file": "El archivo no es una imagen válida."}) from exc

    if img.mode != "RGB":
        img = img.convert("RGB")
    img.thumbnail((MAX_SIDE_PX, MAX_SIDE_PX))
    out = io.BytesIO()
    img.save(out, format="JPEG", quality=JPEG_QUALITY, optimize=True)
    return out.getvalue(), img.width, img.height


def set_employee_photo(*, request, actor, employee: Employee, raw: bytes) -> EmployeePhoto:
    # El formato lo valida Pillow con los BYTES (el content-type del cliente
    # miente fácil y rechazaría subidas legítimas, p. ej. octet-stream).
    if len(raw) > MAX_UPLOAD_BYTES:
        raise ValidationError({"file": "La foto supera el máximo de 8 MB."})

    jpeg, width, height = normalize_photo(raw)
    photo, _created = EmployeePhoto.objects.update_or_create(
        employee=employee,
        defaults={
            "image_data": base64.b64encode(jpeg).decode("ascii"),
            "content_type": "image/jpeg",
            "byte_size": len(jpeg),
            "width": width,
            "height": height,
            "updated_by": actor,
        },
    )
    write_event(
        request=request,
        module="HR",
        event_type="HR_EMPLOYEE_PHOTO_SET",
        reason_code="OK",
        actor_user=actor,
        subject_type="EMPLOYEE",
        subject_id=str(employee.id),
        metadata={"byte_size": len(jpeg), "width": width, "height": height},
    )
    return photo


def remove_employee_photo(*, request, actor, employee: Employee) -> bool:
    deleted, _ = EmployeePhoto.objects.filter(employee=employee).delete()
    if deleted:
        write_event(
            request=request,
            module="HR",
            event_type="HR_EMPLOYEE_PHOTO_REMOVED",
            reason_code="OK",
            actor_user=actor,
            subject_type="EMPLOYEE",
            subject_id=str(employee.id),
            metadata={},
        )
    return bool(deleted)
