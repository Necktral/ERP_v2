from django.contrib.auth.models import AbstractUser
from django.db import models


class User(AbstractUser):
    email = models.EmailField(unique=True, blank=True, null=True)

    # Flujo onboarding:
    # - empleado creado por admin: entra con contraseña provisional y el sistema obliga a cambiarla
    must_change_password = models.BooleanField(default=False)
