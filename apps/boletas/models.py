from django.conf import settings
from django.db import models

from apps.eventos.models import Evento, Localidad


class Boleta(models.Model):
    """
    Entidad más compleja del sistema: nunca se instancia directamente en el
    Service ni en la vista. Toda creación pasa por `BoletaBuilder`
    (`domain/builders/boleta_builder.py`), que garantiza usuario, evento,
    localidad con cupo, precio y código QR consistentes antes de persistir.
    """

    class Estado(models.TextChoices):
        RESERVADA = "RESERVADA", "Reservada"
        PAGADA = "PAGADA", "Pagada"
        CANCELADA = "CANCELADA", "Cancelada"

    usuario = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="boletas"
    )
    evento = models.ForeignKey(Evento, on_delete=models.CASCADE, related_name="boletas")
    localidad = models.ForeignKey(
        Localidad, on_delete=models.PROTECT, related_name="boletas"
    )
    codigo_qr = models.CharField(max_length=36, unique=True)
    precio = models.DecimalField(max_digits=10, decimal_places=2)
    estado = models.CharField(
        max_length=10, choices=Estado.choices, default=Estado.RESERVADA
    )
    reservada_en = models.DateTimeField()
    creado_en = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-creado_en"]

    def __str__(self) -> str:
        return f"Boleta {self.codigo_qr} - {self.estado}"
