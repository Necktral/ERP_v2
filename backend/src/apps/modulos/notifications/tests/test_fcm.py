"""Tests del adaptador FCM (Fase B): push gateado por setting + baja de tokens inválidos."""
from __future__ import annotations

import uuid
from unittest.mock import patch

import pytest
from django.contrib.auth import get_user_model
from django.test import override_settings

from apps.modulos.iam.models import OrgUnit
from apps.modulos.notifications.models import DeviceToken, DevicePlatform
from apps.modulos.notifications.senders import FcmSender, RecordSender, get_active_sender
from apps.modulos.notifications.services import emit_notification

User = get_user_model()
UT = OrgUnit.UnitType


def _company():
    t = uuid.uuid4().hex[:6]
    holding = OrgUnit.objects.create(unit_type=UT.HOLDING, name=f"H{t}", code=f"H-{t}")
    return OrgUnit.objects.create(unit_type=UT.COMPANY, parent=holding, name=f"C{t}", code=f"C-{t}")


def _user():
    t = uuid.uuid4().hex[:8]
    return User.objects.create_user(username=f"u_{t}", email=f"u_{t}@t.local", password="pass12345")


def _token(user, company, token="t1"):
    return DeviceToken.objects.create(user=user, company=company, platform=DevicePlatform.ANDROID, token=token)


def test_get_active_sender_default_is_record():
    assert isinstance(get_active_sender(), RecordSender)


@override_settings(NOTIFICATIONS_FCM_ENABLED=True, NOTIFICATIONS_FCM_ENDPOINT="http://fcm.test",
                   NOTIFICATIONS_FCM_SERVER_KEY="k")
def test_get_active_sender_fcm_when_enabled():
    assert isinstance(get_active_sender(), FcmSender)


@pytest.mark.django_db
@override_settings(NOTIFICATIONS_FCM_ENABLED=True, NOTIFICATIONS_FCM_ENDPOINT="http://fcm.test",
                   NOTIFICATIONS_FCM_SERVER_KEY="k")
def test_emit_pushes_to_device_and_keeps_valid_token():
    company = _company()
    user = _user()
    tok = _token(user, company)
    with patch("apps.modulos.notifications.senders._fcm_post", return_value=(200, "{}")) as mock_post:
        rec = emit_notification(company=company, branch=None, recipient_user_id=user.id,
                                event_type="MaintenanceDue", title="t", body="b", dedupe_key="d1")
    assert rec.status == "SENT"
    assert mock_post.called
    tok.refresh_from_db()
    assert tok.is_active is True


@pytest.mark.django_db
@override_settings(NOTIFICATIONS_FCM_ENABLED=True, NOTIFICATIONS_FCM_ENDPOINT="http://fcm.test",
                   NOTIFICATIONS_FCM_SERVER_KEY="k")
def test_invalid_token_is_deactivated():
    company = _company()
    user = _user()
    tok = _token(user, company)
    with patch("apps.modulos.notifications.senders._fcm_post", return_value=(404, "UNREGISTERED")):
        rec = emit_notification(company=company, branch=None, recipient_user_id=user.id,
                                event_type="MaintenanceDue", title="t", body="b", dedupe_key="d2")
    assert rec.status == "SENT"  # in-app entregado pese a token inválido
    tok.refresh_from_db()
    assert tok.is_active is False


@pytest.mark.django_db
def test_no_push_when_fcm_disabled():
    company = _company()
    user = _user()
    _token(user, company)
    with patch("apps.modulos.notifications.senders._fcm_post") as mock_post:
        emit_notification(company=company, branch=None, recipient_user_id=user.id,
                          event_type="X", title="t", dedupe_key="d3")
    assert not mock_post.called  # RecordSender no hace push
