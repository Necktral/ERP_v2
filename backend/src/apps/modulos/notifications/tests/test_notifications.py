"""Tests del módulo notifications: emisión idempotente por dedupe_key, ruteo por rol,
consumo idempotente del outbox (InboxEvent), y registro de device-token vía HTTP/RBAC.
"""
from __future__ import annotations

import uuid

import pytest
from django.contrib.auth import get_user_model
from rest_framework.test import APIClient

from apps.modulos.integration.services import publish_outbox_event
from apps.modulos.notifications.models import NotificationRecord
from apps.modulos.notifications.services import (
    dispatch_fleet_notifications,
    emit_notification,
    notify_roles,
)
from apps.modulos.iam.models import OrgUnit, UserMembership
from apps.modulos.rbac.models import Permission, Role, RoleAssignment, RolePermission

User = get_user_model()
UT = OrgUnit.UnitType


def _scope():
    t = uuid.uuid4().hex[:6]
    holding = OrgUnit.objects.create(unit_type=UT.HOLDING, name=f"H{t}", code=f"H-{t}")
    company = OrgUnit.objects.create(unit_type=UT.COMPANY, parent=holding, name=f"C{t}", code=f"C-{t}")
    branch = OrgUnit.objects.create(unit_type=UT.BRANCH, parent=company, name=f"B{t}", code=f"B-{t}")
    return company, branch


def _user():
    t = uuid.uuid4().hex[:8]
    return User.objects.create_user(username=f"u_{t}", email=f"u_{t}@t.local", password="pass12345")


@pytest.mark.django_db
def test_emit_notification_idempotent_by_dedupe_key():
    company, _branch = _scope()
    u = _user()
    r1 = emit_notification(company=company, branch=None, recipient_user_id=u.id,
                           event_type="X", title="t", dedupe_key="k1")
    r2 = emit_notification(company=company, branch=None, recipient_user_id=u.id,
                           event_type="X", title="t", dedupe_key="k1")
    assert r1.id == r2.id
    assert NotificationRecord.objects.filter(dedupe_key="k1").count() == 1
    assert r1.status == "SENT"  # RecordSender entrega in-app


@pytest.mark.django_db
def test_notify_roles_resolves_users_in_scope():
    company, branch = _scope()
    role = Role.objects.create(name="fleet_supervisor", is_active=True)
    target = _user()
    RoleAssignment.objects.create(user=target, role=role, org_unit=company, is_active=True)
    other = _user()  # sin rol → no recibe
    RoleAssignment.objects.create(user=other, role=Role.objects.create(name=f"x_{uuid.uuid4().hex[:6]}"),
                                  org_unit=company, is_active=True)

    recs = notify_roles(company=company, branch=branch, roles=["fleet_supervisor"],
                        event_type="MaintenanceDue", title="m", dedupe_prefix="evt1")
    assert len(recs) == 1
    assert recs[0].recipient_user_id == target.id


@pytest.mark.django_db
def test_dispatch_consumes_outbox_once():
    company, branch = _scope()
    role = Role.objects.create(name="fleet_supervisor", is_active=True)
    target = _user()
    RoleAssignment.objects.create(user=target, role=role, org_unit=company, is_active=True)

    publish_outbox_event(
        source_module="FLEET", event_type="MaintenanceDue",
        payload={"asset_code": "LC1", "maintenance_type": "Aceite"},
        company=company, branch=branch,
    )
    r1 = dispatch_fleet_notifications()
    r2 = dispatch_fleet_notifications()  # 2ª vez: InboxEvent ya PROCESSED
    assert r1["emitted"] == 1
    assert r2["emitted"] == 0
    assert NotificationRecord.objects.filter(recipient_user=target, event_type="MaintenanceDue").count() == 1


def _client(user, company, branch, perms):
    UserMembership.objects.get_or_create(user=user, org_unit=company, defaults={"is_active": True})
    UserMembership.objects.get_or_create(user=user, org_unit=branch, defaults={"is_active": True})
    role = Role.objects.create(name=f"r_{uuid.uuid4().hex[:8]}", is_active=True)
    for code in perms:
        perm, _ = Permission.objects.get_or_create(code=code, defaults={"description": code, "is_active": True})
        RolePermission.objects.get_or_create(role=role, permission=perm)
    RoleAssignment.objects.create(user=user, role=role, org_unit=company, is_active=True)
    RoleAssignment.objects.create(user=user, role=role, org_unit=branch, is_active=True)
    c = APIClient()
    login = c.post("/api/auth/login/", {"username": user.username, "password": "pass12345"},
                   format="json", HTTP_X_AUTH_TRANSPORT="header")
    assert login.status_code == 200, login.data
    c.credentials(HTTP_AUTHORIZATION=f"Bearer {login.data.get('access')}")
    c.defaults["HTTP_X_AUTH_TRANSPORT"] = "header"
    c.defaults["HTTP_X_COMPANY_ID"] = str(company.id)
    c.defaults["HTTP_X_BRANCH_ID"] = str(branch.id)
    return c


@pytest.mark.django_db
def test_device_token_register_http():
    company, branch = _scope()
    api = _client(_user(), company, branch, ["notifications.device.register"])
    r = api.post("/api/notifications/device-token/",
                 {"platform": "ANDROID", "token": "tok-abc"}, format="json")
    assert r.status_code == 200, r.data
    assert r.data["platform"] == "ANDROID" and r.data["is_active"] is True
