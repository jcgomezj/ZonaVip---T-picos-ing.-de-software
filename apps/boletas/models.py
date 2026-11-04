from django.conf import settings
from django.db import models

from apps.eventos.models import Evento, Localidad


class Pago(models.Model):
    """Cobro de una compra (una compra de N boletas = UN pago).

    `idempotency_key` evita el doble cobro por doble clic / reintento: la
    misma clave del mismo usuario devuelve el resultado original."""

    class Estado(models.TextChoices):
        APROBADO = "APROBADO", "Aprobado"
        REEMBOLSADO = "REEMBOLSADO", "Reembolsado"

    usuario = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="pagos")
    evento = models.ForeignKey(Evento, on_delete=models.PROTECT, related_name="pagos")
    localidad = models.ForeignKey(Localidad, on_delete=models.PROTECT, related_name="pagos")
    cantidad = models.PositiveSmallIntegerField()
    monto = models.DecimalField(max_digits=12, decimal_places=2)
    metodo = models.CharField(max_length=10, default="TARJETA")
    estado = models.CharField(max_length=12, choices=Estado.choices, default=Estado.APROBADO)
    referencia = models.CharField(max_length=40, unique=True)
    idempotency_key = models.CharField(max_length=64, null=True, blank=True)
    creado_en = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-creado_en"]
        constraints = [
            models.UniqueConstraint(fields=["usuario", "idempotency_key"], name="uniq_pago_usuario_idem"),
        ]
        indexes = [models.Index(fields=["evento", "estado"], name="idx_pago_evento_estado")]

    def __str__(self) -> str:
        return f"Pago {self.referencia} - {self.estado}"


class Boleta(models.Model):
    """
    Nunca se instancia directamente: toda creación pasa por `BoletaBuilder`.

    Ciclo de vida:  RESERVADA -> PAGADA -> USADA (check-in)
                    RESERVADA/PAGADA -> CANCELADA
    """

    class Estado(models.TextChoices):
        RESERVADA = "RESERVADA", "Reservada"
        PAGADA = "PAGADA", "Pagada"
        USADA = "USADA", "Usada"
        CANCELADA = "CANCELADA", "Cancelada"

    class MotivoCancelacion(models.TextChoices):
        USUARIO = "USUARIO", "Cancelada por el usuario"
        EVENTO_CANCELADO = "EVENTO_CANCELADO", "Evento cancelado"
        RESERVA_EXPIRADA = "RESERVA_EXPIRADA", "Reserva expirada"

    usuario = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="boletas")
    evento = models.ForeignKey(Evento, on_delete=models.CASCADE, related_name="boletas")
    localidad = models.ForeignKey(Localidad, on_delete=models.PROTECT, related_name="boletas")
    pago = models.ForeignKey(Pago, on_delete=models.PROTECT, null=True, blank=True, related_name="boletas")
    codigo_qr = models.CharField(max_length=36, unique=True)
    precio = models.DecimalField(max_digits=10, decimal_places=2)
    estado = models.CharField(max_length=10, choices=Estado.choices, default=Estado.RESERVADA)
    reservada_en = models.DateTimeField()
    expira_en = models.DateTimeField(null=True, blank=True)
    usada_en = models.DateTimeField(null=True, blank=True)
    validada_por = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True,
        related_name="boletas_validadas",
    )
    motivo_cancelacion = models.CharField(max_length=20, choices=MotivoCancelacion.choices, blank=True)
    creado_en = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-creado_en"]
        indexes = [
            models.Index(fields=["usuario", "-creado_en"], name="idx_boleta_usr_creado"),
            models.Index(fields=["evento", "estado"], name="idx_boleta_evento_estado"),
            models.Index(fields=["localidad", "estado"], name="idx_boleta_loc_estado"),
            models.Index(fields=["estado", "expira_en"], name="idx_boleta_estado_expira"),
        ]

    def __str__(self) -> str:
        return f"Boleta {self.codigo_qr} - {self.estado}"
