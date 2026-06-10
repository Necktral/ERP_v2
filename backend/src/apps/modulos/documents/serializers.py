from __future__ import annotations

import base64
import binascii

from rest_framework import serializers

from .models import DocumentType, ScannedDocument

MAX_IMAGE_BYTES = 8 * 1024 * 1024  # 8 MB


def _decode_base64_image(value: str) -> bytes:
    raw = (value or "").strip()
    if raw.startswith("data:"):
        # data:<mime>;base64,<payload>
        _, _, raw = raw.partition(",")
    try:
        data = base64.b64decode(raw, validate=True)
    except (binascii.Error, ValueError) as exc:
        raise serializers.ValidationError("Base64 inválido.") from exc
    if not data:
        raise serializers.ValidationError("Imagen vacía.")
    if len(data) > MAX_IMAGE_BYTES:
        raise serializers.ValidationError("Imagen demasiado grande (máx 8 MB).")
    return data


class ScannedDocumentUploadSerializer(serializers.Serializer):
    doc_type = serializers.ChoiceField(choices=DocumentType.choices, default=DocumentType.GENERAL)
    image_base64 = serializers.CharField()
    content_type = serializers.CharField(required=False, allow_blank=True, default="")
    branch_id = serializers.IntegerField(required=False, allow_null=True)

    def validate_image_base64(self, value: str) -> bytes:
        return _decode_base64_image(value)


class ScannedDocumentReviewSerializer(serializers.Serializer):
    extracted_fields = serializers.JSONField(required=False)
    doc_type = serializers.ChoiceField(choices=DocumentType.choices, required=False)


class ScannedDocumentSerializer(serializers.ModelSerializer):
    class Meta:
        model = ScannedDocument
        fields = (
            "id",
            "doc_type",
            "status",
            "content_type",
            "byte_size",
            "ocr_text",
            "extracted_fields",
            "ocr_engine",
            "ocr_error",
            "linked_object_type",
            "linked_object_id",
            "created_at",
            "processed_at",
            "reviewed_at",
        )
        read_only_fields = fields
