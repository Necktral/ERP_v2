from django.contrib.auth.models import AbstractUser
from django.db import models


class User(AbstractUser):
    email = models.EmailField(unique=True, blank=True, null=True)

    # Flujo onboarding:
    # - empleado creado por admin: entra con contraseña provisional y el sistema obliga a cambiarla
    must_change_password = models.BooleanField(default=False)

    # Compatibilidad con esquemas existentes (algunas BD tienen esta columna NOT NULL)
    is_setup_complete = models.BooleanField(default=False)
