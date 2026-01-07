from __future__ import annotations

from typing import TypedDict, Optional
from django.db import transaction
from django.utils import timezone
from apps.iam.models import OrgUnit, UserMembership, AdminGrant, OrgClosure
from apps.org.models import CompanyProfile, BranchProfile
from django.contrib.auth import get_user_model

User = get_user_model()


class InitialAdminData(TypedDict):
    username: str
    email: str
    password: str
    first_name: str
    last_name: str


class OrganizationData(TypedDict):
    holding_name: str
    company_name: str
    company_tax_id: str
    branch_name: str
    branch_address: str


def is_system_fresh() -> bool:
    """Returns True if there are no users in the system."""
    return User.objects.count() == 0


@transaction.atomic
def create_initial_admin(data: InitialAdminData) -> User:
    """Creates the first superuser of the system."""
    if not is_system_fresh():
        raise ValueError("System is not fresh. Cannot create initial admin.")
    
    user = User.objects.create_superuser(
        username=data["username"],
        email=data["email"],
        password=data["password"],
        first_name=data["first_name"],
        last_name=data["last_name"],
        is_setup_complete=False,  # Setup not complete until Org is created
        must_change_password=False, # Initial admin sets their own password
        pw_last_changed=timezone.now()
    )
    return user


@transaction.atomic
def bootstrap_organization(user: User, data: OrganizationData) -> dict[str, OrgUnit]:
    """
    Creates the initial Holding -> Company -> Branch structure 
    and links the user to them.
    """
    
    # 1. Create Holding
    holding = OrgUnit.objects.create(
        unit_type=OrgUnit.UnitType.HOLDING,
        name=data["holding_name"],
        code="HOLDING-001"
    )

    # 2. Create Company
    company = OrgUnit.objects.create(
        unit_type=OrgUnit.UnitType.COMPANY,
        name=data["company_name"],
        parent=holding,
        code="COMP-001"
    )
    CompanyProfile.objects.create(
        company=company,
        tax_id=data["company_tax_id"],
        legal_name=data["company_name"]
    )

    # 3. Create Branch
    branch = OrgUnit.objects.create(
        unit_type=OrgUnit.UnitType.BRANCH,
        name=data["branch_name"],
        parent=company,
        code="BRANCH-001"
    )
    BranchProfile.objects.create(
        branch=branch,
        address=data["branch_address"]
    )

    # 4. Link User (Membership)
    # Grant membership to the Holding (cascades? No, usually explicit)
    # For simplicity, let's give membership to all 3 levels or just Holding?
    # Usually membership is at specific levels. Let's add to all for full access.
    
    UserMembership.objects.create(user=user, org_unit=holding)
    UserMembership.objects.create(user=user, org_unit=company)
    UserMembership.objects.create(user=user, org_unit=branch)

    # 5. Admin Grants
    # Grant full capabilities on the Holding (applies to subtree)
    for cap in AdminGrant.Capability:
        AdminGrant.objects.create(
            user=user,
            org_unit=holding,
            capability=cap,
            applies_to_subtree=True,
            granted_by=user  # Self-granted
        )

    # 6. Mark user setup as complete
    user.is_setup_complete = True
    user.save()

    return {
        "holding": holding,
        "company": company,
        "branch": branch
    }
