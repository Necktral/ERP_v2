"""Modelo base del subsistema IDP (Intelligent Document Processing).

`ScannedDocument` es la unidad del pipeline: captura → OCR → extracción → revisión →
integración. F1 cubre captura + OCR + revisión; F2 agrega la etapa de extracción
determinista (estado EXTRACTED = borrador con campos, cola de revisión humana).
`linked_object_*` queda reservado para F4 (integración).
"""
from __future__ import annotations

from django.conf import settings
from django.db import models
from django.utils import timezone

from apps.modulos.iam.models import OrgUnit


class DocumentType(models.TextChoices):
    GENERAL = "GENERAL", "General"
    INVOICE = "INVOICE", "Factura/Recibo"
    FUEL_TICKET = "FUEL_TICKET", "Ticket de combustible"
    PAYROLL = "PAYROLL", "Planilla/Nómina"
    REMISION = "REMISION", "Remisión/Envío (movimiento entre fincas/bodegas)"


class ScanStatus(models.TextChoices):
    PENDING_OCR = "PENDING_OCR", "Pendiente de OCR"
    PROCESSED = "PROCESSED", "Procesado (OCR)"
    EXTRACTED = "EXTRACTED", "Campos extraídos (borrador, pendiente de revisión)"
    REVIEWED = "REVIEWED", "Revisado"
    FAILED = "FAILED", "Falló OCR"


class ScannedDocument(models.Model):
    class Meta:
        app_label = "documents"
        ordering = ["-created_at"]
        indexes = [
            models.Index(fields=["company", "status"]),
            models.Index(fields=["company", "doc_type"]),
        ]

    company = models.ForeignKey(
        OrgUnit, on_delete=models.PROTECT, related_name="scanned_documents"
    )
    branch = models.ForeignKey(
        OrgUnit,
        null=True,
        blank=True,
        on_delete=models.PROTECT,
        related_name="branch_scanned_documents",
    )
    doc_type = models.CharField(
        max_length=32, choices=DocumentType.choices, default=DocumentType.GENERAL
    )
    status = models.CharField(
        max_length=16, choices=ScanStatus.choices, default=ScanStatus.PENDING_OCR
    )

    # Almacenamiento de la imagen. F1 = en la DB (base64) detrás de una abstracción de
    # storage; `storage_backend` permite migrar a object storage (MinIO) sin tocar el
    # contrato: cuando sea "object", la imagen vive en `image_ref` (clave/URL).
    storage_backend = models.CharField(max_length=16, default="db")
    image_data = models.TextField(blank=True, default="")
    image_ref = models.CharField(max_length=512, blank=True, default="")
    content_type = models.CharField(max_length=64, blank=True, default="")
    byte_size = models.PositiveIntegerField(default=0)

    # Resultado del pipeline IDP.
    ocr_text = models.TextField(blank=True, default="")
    extracted_fields = models.JSONField(default=dict, blank=True)
    ocr_engine = models.CharField(max_length=32, blank=True, default="")
    ocr_error = models.CharField(max_length=255, blank=True, default="")

    # Integración (F4): enlace genérico al objeto de negocio (factura/ticket/planilla).
    linked_object_type = models.CharField(max_length=64, blank=True, default="")
    linked_object_id = models.CharField(max_length=64, blank=True, default="")

    uploaded_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        on_delete=models.SET_NULL,
        related_name="uploaded_documents",
    )
    reviewed_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="reviewed_documents",
    )

    created_at = models.DateTimeField(default=timezone.now, editable=False)
    processed_at = models.DateTimeField(null=True, blank=True)
    reviewed_at = models.DateTimeField(null=True, blank=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self) -> str:
        return f"ScannedDocument(id={self.pk}, type={self.doc_type}, status={self.status})"
