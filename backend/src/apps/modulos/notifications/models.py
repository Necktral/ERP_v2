"""Notificaciones (transversal): registro de dispositivos + registro de notificación.

Diseño desacoplado (patrón D6 del plan Fleet): el productor (p.ej. fleet) sólo publica
`OutboxEvent`; este módulo los consume (idempotencia por `integration.InboxEvent`) y emite
`NotificationRecord` a los usuarios con el rol correcto. El ENVÍO es un adaptador (`senders.py`):
en Fase A el canal es RECORD (in-app, el propio registro); FCM/push entra en Fase B sin tocar
el dominio.
"""
from __future__ import annotations

from django.conf import settings
from django.db import models
from django.utils import timezone


class DevicePlatform(models.TextChoices):
    ANDROID = "ANDROID", "Android"
    IOS = "IOS", "iOS"
    WEB = "WEB", "Web"


class DeviceToken(models.Model):
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="notification_tokens")
    company = models.ForeignKey("iam.OrgUnit", on_delete=models.PROTECT, related_name="notification_tokens")
    platform = models.CharField(max_length=8, choices=DevicePlatform.choices)
    token = models.CharField(max_length=512)
    is_active = models.BooleanField(default=True)
    last_seen = models.DateTimeField(default=timezone.now)
    created_at = models.DateTimeField(default=timezone.now, editable=False)

    class Meta:
        app_label = "notifications"
        constraints = [
            models.UniqueConstraint(fields=["user", "token"], name="uq_devicetoken_user_token"),
        ]
        indexes = [
            models.Index(fields=["user", "is_active"], name="ix_devtok_user_active"),
            models.Index(fields=["company", "is_active"], name="ix_devtok_co_active"),
        ]

    def __str__(self) -> str:
        return f"DeviceToken<{self.user_id}:{self.platform}>"


class NotificationChannel(models.TextChoices):
    RECORD = "RECORD", "In-app record"
    PUSH = "PUSH", "Push (FCM)"


class NotificationStatus(models.TextChoices):
    PENDING = "PENDING", "Pending"
    SENT = "SENT", "Sent"
    FAILED = "FAILED", "Failed"
    SKIPPED = "SKIPPED", "Skipped"


class NotificationRecord(models.Model):
    company = models.ForeignKey("iam.OrgUnit", on_delete=models.PROTECT, related_name="notifications_company")
    branch = models.ForeignKey(
        "iam.OrgUnit", null=True, blank=True, on_delete=models.PROTECT, related_name="notifications_branch"
    )
    recipient_user = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="notifications_received"
    )
    event_type = models.CharField(max_length=128)
    title = models.CharField(max_length=200)
    body = models.CharField(max_length=500, blank=True, default="")
    payload_json = models.JSONField(default=dict, blank=True)
    channel = models.CharField(max_length=8, choices=NotificationChannel.choices, default=NotificationChannel.RECORD)
    status = models.CharField(max_length=8, choices=NotificationStatus.choices, default=NotificationStatus.PENDING)
    error = models.CharField(max_length=255, blank=True, default="")
    # Idempotencia: una notificación por (evento de origen, destinatario).
    dedupe_key = models.CharField(max_length=200, unique=True)
    created_at = models.DateTimeField(default=timezone.now, editable=False)
    sent_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        app_label = "notifications"
        indexes = [
            models.Index(fields=["recipient_user", "status", "created_at"], name="ix_notif_user_status"),
            models.Index(fields=["company", "event_type", "created_at"], name="ix_notif_co_event"),
        ]

    def __str__(self) -> str:
        return f"Notification<{self.event_type}:{self.recipient_user_id}:{self.status}>"
