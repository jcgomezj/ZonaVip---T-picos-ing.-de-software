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

    class Meta:
        indexes = [
            models.Index(fields=["verificado"], name="idx_organizador_verificado"),
        ]

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

    # Imagen de portada opcional. Si no se define, el frontend usa una
    # imagen de concierto por defecto (ver propiedad `imagen_url`).
    imagen = models.URLField(blank=True, help_text="URL de la imagen de portada del evento.")

    class TipoRecinto(models.TextChoices):
        ESTADIO = "ESTADIO", "Estadio (tribunas)"
        ABIERTO = "ABIERTO", "Espacio abierto / parque"
        CERRADO = "CERRADO", "Arena / teatro"

    # Define el flujo de compra: en un ESTADIO el usuario elige tribuna; en un
    # espacio ABIERTO la localidad es única (Gramilla / General).
    tipo_recinto = models.CharField(
        max_length=10, choices=TipoRecinto.choices, default=TipoRecinto.CERRADO
    )

    class Meta:
        ordering = ["fecha_evento"]
        indexes = [
            models.Index(fields=["estado", "fecha_evento"], name="idx_evento_estado_fecha"),
            models.Index(
                fields=["categoria", "estado", "fecha_evento"],
                name="idx_evento_cat_est_fecha",
            ),
            models.Index(fields=["fecha_evento"], name="idx_evento_fecha"),
            models.Index(fields=["titulo"], name="idx_evento_titulo"),
        ]

    def __str__(self) -> str:
        return f"{self.titulo} ({self.fecha_evento:%Y-%m-%d})"

    # Galería de respaldo: fotos de conciertos (Unsplash, libres de uso).
    _IMAGENES_DEFECTO = [
        "https://images.unsplash.com/photo-1501386761578-eac5c94b800a?w=800&q=70&auto=format&fit=crop",
        "https://images.unsplash.com/photo-1540039155733-5bb30b53aa14?w=800&q=70&auto=format&fit=crop",
        "https://images.unsplash.com/photo-1459749411175-04bf5292ceea?w=800&q=70&auto=format&fit=crop",
        "https://images.unsplash.com/photo-1493225457124-a3eb161ffa5f?w=800&q=70&auto=format&fit=crop",
        "https://images.unsplash.com/photo-1429962714451-bb934ecdc4ec?w=800&q=70&auto=format&fit=crop",
        "https://images.unsplash.com/photo-1514525253161-7a46d19cd819?w=800&q=70&auto=format&fit=crop",
    ]

    @property
    def imagen_url(self) -> str:
        """URL de portada: la configurada o una foto de concierto por defecto
        (elegida de forma estable según el id, para que no cambie entre cargas)."""
        if self.imagen:
            return self.imagen
        indice = (self.pk or 0) % len(self._IMAGENES_DEFECTO)
        return self._IMAGENES_DEFECTO[indice]

    @property
    def primera_localidad(self) -> "Localidad | None":
        """Devuelve la primera localidad usando el prefetch cache si existe, evitando N+1 queries."""
        locs = list(self.localidades.all())
        return locs[0] if locs else None


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
        indexes = [
            models.Index(fields=["evento", "tipo"], name="idx_localidad_evento_tipo"),
        ]
        constraints = [
            models.CheckConstraint(
                check=models.Q(vendidas__lte=models.F("cupo")),
                name="check_localidad_vendidas_cupo",
            ),
            models.CheckConstraint(
                check=models.Q(vendidas__gte=0),
                name="check_localidad_vendidas_positivas",
            ),
        ]

    def __str__(self) -> str:
        return f"{self.nombre} - {self.evento.titulo}"

    def hay_cupo(self) -> bool:
        return self.vendidas < self.cupo
