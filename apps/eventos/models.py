from django.conf import settings
from django.db import models


class CategoriaEvento(models.Model):
    """Clasificación simple de eventos (Concierto, Teatro, Deportivo, etc.)."""

    nombre = models.CharField(max_length=80, unique=True)
    descripcion = models.CharField(max_length=255, blank=True)

    class Meta:
        verbose_name = "Categoría de evento"
        verbose_name_plural = "Categorías de evento"
        ordering = ["nombre"]

    def __str__(self) -> str:
        return self.nombre


class Organizador(models.Model):
    """Perfil de negocio de un Usuario que publica eventos."""

    usuario = models.OneToOneField(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="perfil_organizador",
    )
    nombre_empresarial = models.CharField(max_length=150)
    nit = models.CharField(max_length=30, blank=True)
    verificado = models.BooleanField(default=False)

    def __str__(self) -> str:
        return self.nombre_empresarial


class Evento(models.Model):
    """Entidad raíz del catálogo. Su ciclo de vida (BORRADOR -> PUBLICADO ->
    CANCELADO/FINALIZADO) es orquestado por servicios (CrearEventoService,
    PublicarEventoService), no por métodos en este modelo."""

    class Estado(models.TextChoices):
        BORRADOR = "BORRADOR", "Borrador"
        PUBLICADO = "PUBLICADO", "Publicado"
        CANCELADO = "CANCELADO", "Cancelado"
        FINALIZADO = "FINALIZADO", "Finalizado"

    organizador = models.ForeignKey(
        Organizador, on_delete=models.CASCADE, related_name="eventos"
    )
    categoria = models.ForeignKey(
        CategoriaEvento, on_delete=models.PROTECT, related_name="eventos"
    )
    titulo = models.CharField(max_length=150)
    descripcion = models.TextField(blank=True)
    lugar = models.CharField(max_length=200)
    fecha_evento = models.DateTimeField()
    estado = models.CharField(
        max_length=12, choices=Estado.choices, default=Estado.BORRADOR
    )
    creado_en = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["fecha_evento"]

    def __str__(self) -> str:
        return f"{self.titulo} ({self.fecha_evento:%Y-%m-%d})"


class Localidad(models.Model):
    """Zona vendible dentro de un Evento (General, VIP, Palco, Platea).

    `hay_cupo()` NO es una regla de negocio compleja: es una lectura
    booleana derivada directamente de dos columnas persistidas
    (`vendidas` y `cupo`), análoga a una `@property`. La decisión de qué
    hacer con esa verdad (rechazar la reserva, lanzar `SinCupoError`, etc.)
    vive en `domain/builders/boleta_builder.py`, no aquí.
    """

    class Tipo(models.TextChoices):
        GENERAL = "GENERAL", "General"
        VIP = "VIP", "VIP"
        PALCO = "PALCO", "Palco"
        PLATEA = "PLATEA", "Platea"

    evento = models.ForeignKey(
        Evento, on_delete=models.CASCADE, related_name="localidades"
    )
    nombre = models.CharField(max_length=80)
    tipo = models.CharField(max_length=10, choices=Tipo.choices, default=Tipo.GENERAL)
    precio = models.DecimalField(max_digits=10, decimal_places=2)
    cupo = models.PositiveIntegerField()
    vendidas = models.PositiveIntegerField(default=0)

    class Meta:
        unique_together = ("evento", "nombre")
        verbose_name_plural = "Localidades"

    def __str__(self) -> str:
        return f"{self.nombre} - {self.evento.titulo}"

    def hay_cupo(self) -> bool:
        return self.vendidas < self.cupo
