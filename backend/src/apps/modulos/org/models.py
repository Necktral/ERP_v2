from __future__ import annotations

from django.core.exceptions import ValidationError
from django.db import models
from django.utils import timezone

from apps.modulos.iam.models import OrgUnit
from django.conf import settings

from .module_catalog import core_codes, is_known


class CompanyProfile(models.Model):
    class Meta:
        app_label = "org"
    """
    Tabla separada para datos de empresa.
    Canon de jerarquía sigue siendo OrgUnit (COMPANY).
    """

    company = models.OneToOneField(OrgUnit, on_delete=models.CASCADE, related_name="company_profile")
    legal_name = models.CharField(max_length=255, blank=True, default="")
    tax_id = models.CharField(max_length=64, blank=True, default="")
    address = models.TextField(blank=True, default="")
    phone = models.CharField(max_length=64, blank=True, default="")
    email = models.EmailField(blank=True, default="")

    created_at = models.DateTimeField(default=timezone.now, editable=False)
    updated_at = models.DateTimeField(auto_now=True)

    def clean(self):
        if self.company.unit_type != OrgUnit.UnitType.COMPANY:
            raise ValidationError("CompanyProfile.company debe ser OrgUnit de tipo COMPANY.")


class BranchProfile(models.Model):
    class Meta:
        app_label = "org"
    """
    Tabla separada para datos de sucursal.
    Canon de jerarquía sigue siendo OrgUnit (BRANCH).
    """

    branch = models.OneToOneField(OrgUnit, on_delete=models.CASCADE, related_name="branch_profile")
    address = models.TextField(blank=True, default="")
    phone = models.CharField(max_length=64, blank=True, default="")
    email = models.EmailField(blank=True, default="")

    # Preferencias por sucursal (Fuel): defaults de UoM por producto.
    # Precedente:
    # - El UI puede “recordar selección” por sucursal para arrancar con valores operativos típicos.
    # - El backend sigue devolviendo ambas unidades en responses/reportes; esto solo define un default.
    FUEL_VOLUME_UOM_CHOICES = [
        ("LITER", "Litro"),
        ("GALLON", "Galón (US)"),
    ]

    fuel_default_volume_uom_gasoline = models.CharField(
        max_length=16,
        choices=FUEL_VOLUME_UOM_CHOICES,
        default="LITER",
    )
    fuel_default_volume_uom_diesel = models.CharField(
        max_length=16,
        choices=FUEL_VOLUME_UOM_CHOICES,
        default="GALLON",
    )

    created_at = models.DateTimeField(default=timezone.now, editable=False)
    updated_at = models.DateTimeField(auto_now=True)

    def clean(self):
        if self.branch.unit_type != OrgUnit.UnitType.BRANCH:
            raise ValidationError("BranchProfile.branch debe ser OrgUnit de tipo BRANCH.")


class UserFuelUoMPreference(models.Model):
    class Meta:
        app_label = "org"
        constraints = [
            models.UniqueConstraint(fields=["user", "branch"], name="uq_user_fuel_uom_pref_user_branch"),
        ]
        indexes = [
            models.Index(fields=["user", "branch"]),
            models.Index(fields=["branch"]),
        ]

    """Preferencias de UoM (Fuel) por usuario y sucursal.

    Precedente:
    - La sucursal define defaults típicos (BranchProfile).
    - El usuario puede sobre-escribirlos para su operación diaria.
    - Si un campo es NULL, se usa el default de sucursal (o el fallback del sistema).
    """

    FUEL_VOLUME_UOM_CHOICES = BranchProfile.FUEL_VOLUME_UOM_CHOICES

    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="fuel_uom_prefs")
    branch = models.ForeignKey(OrgUnit, on_delete=models.CASCADE, related_name="fuel_uom_prefs")

    gasoline_volume_uom = models.CharField(max_length=16, choices=FUEL_VOLUME_UOM_CHOICES, null=True, blank=True)
    diesel_volume_uom = models.CharField(max_length=16, choices=FUEL_VOLUME_UOM_CHOICES, null=True, blank=True)

    created_at = models.DateTimeField(default=timezone.now, editable=False)
    updated_at = models.DateTimeField(auto_now=True)

    def clean(self):
        if self.branch.unit_type != OrgUnit.UnitType.BRANCH:
            raise ValidationError("UserFuelUoMPreference.branch debe ser OrgUnit de tipo BRANCH.")


class CompanyModule(models.Model):
    """Override de habilitación de un módulo para una empresa.

    Ausencia de fila = se usa el ``default_enabled`` del catálogo
    (ver ``apps.modulos.org.module_catalog``). Los módulos *core* nunca se
    persisten aquí: son siempre activos y no togglables.
    """

    class Meta:
        app_label = "org"
        constraints = [
            models.UniqueConstraint(fields=["company", "module_code"], name="uq_company_module"),
        ]
        indexes = [
            models.Index(fields=["company", "is_enabled"]),
        ]

    company = models.ForeignKey(OrgUnit, on_delete=models.PROTECT, related_name="company_modules")
    module_code = models.CharField(max_length=64)
    is_enabled = models.BooleanField(default=True)

    updated_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="company_module_updates",
    )
    created_at = models.DateTimeField(default=timezone.now, editable=False)
    updated_at = models.DateTimeField(auto_now=True)

    def clean(self):
        if self.company.unit_type != OrgUnit.UnitType.COMPANY:
            raise ValidationError("CompanyModule.company debe ser OrgUnit de tipo COMPANY.")
        if not is_known(self.module_code):
            raise ValidationError(f"Módulo desconocido: {self.module_code}")
        if self.module_code in core_codes():
            raise ValidationError(f"El módulo core '{self.module_code}' no es configurable.")
