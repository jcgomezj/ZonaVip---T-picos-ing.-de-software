from django.contrib.auth.models import AbstractUser
from django.db import models


class Usuario(AbstractUser):
    """
    Extiende el usuario nativo de Django. Este archivo es solo persistencia:
    tipos de dato y constraints a nivel de columna. Ninguna regla de negocio
    (por ejemplo, quién puede crear eventos) vive aquí; eso lo decide el
    Service Layer en `application/services.py`.
    """

    telefono = models.CharField(max_length=20, blank=True)
    es_organizador = models.BooleanField(
        default=False,
        help_text="Indica si este usuario tiene (o puede solicitar) un perfil de Organizador.",
    )

    def __str__(self) -> str:
        return self.username
