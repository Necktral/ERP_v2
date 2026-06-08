from __future__ import annotations

from django.db import migrations


def forwards(apps, schema_editor):
    UserRole = apps.get_model("rbac", "UserRole")
    RoleAssignment = apps.get_model("rbac", "RoleAssignment")
    UserMembership = apps.get_model("iam", "UserMembership")

    memberships_by_user: dict[int, set[int]] = {}
    memberships = (
        UserMembership.objects.filter(
            is_active=True,
            org_unit__unit_type__in=("COMPANY", "BRANCH"),
        )
        .values_list("user_id", "org_unit_id")
        .iterator()
    )
    for user_id, org_unit_id in memberships:
        memberships_by_user.setdefault(int(user_id), set()).add(int(org_unit_id))

    for user_role in UserRole.objects.values("id", "user_id", "role_id").iterator():
        user_id = int(user_role["user_id"])
        role_id = int(user_role["role_id"])
        origin_ref = f"legacy-userrole:{int(user_role['id'])}"
        for org_unit_id in memberships_by_user.get(user_id, set()):
            RoleAssignment.objects.update_or_create(
                user_id=user_id,
                role_id=role_id,
                org_unit_id=org_unit_id,
                origin="SYSTEM",
                defaults={
                    "origin_ref": origin_ref,
                    "is_active": True,
                    "granted_by_id": None,
                },
            )


def backwards(apps, schema_editor):
    RoleAssignment = apps.get_model("rbac", "RoleAssignment")
    RoleAssignment.objects.filter(origin="SYSTEM", origin_ref__startswith="legacy-userrole:").delete()


class Migration(migrations.Migration):
    dependencies = [
        ("iam", "0005_approvalrequest"),
        ("rbac", "0005_rename_rbac_perm_active_code_idx_rbac_permis_is_acti_42ab9f_idx_and_more"),
    ]

    operations = [
        migrations.RunPython(forwards, backwards),
    ]
