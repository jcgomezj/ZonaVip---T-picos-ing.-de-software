"""
Presenters (view-models) del frontend web.

Traducen entidades del ORM a lo que la UI necesita pintar: niveles de
disponibilidad, precio "desde", porcentaje vendido y el payload JSON del
checkout. Son reglas de PRESENTACIÓN (cuándo mostrar "¡Últimos asientos!"),
no de negocio: la decisión de si se puede reservar sigue viviendo en
`domain/builders/boleta_builder.py`.

Todos los cálculos recorren `evento.localidades.all()`, que debe venir
precargado con `prefetch_related("localidades")` -> cero queries extra.
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from functools import cached_property

from apps.eventos.models import Evento, Localidad

# Umbrales de urgencia. "Últimos asientos" = quedan <= 15 % del cupo o
# <= 10 sillas (lo que sea mayor), para que no salte en zonas enormes con
# cientos de sillas libres ni deje de saltar en palcos pequeños.
ULTIMOS_MIN_SILLAS = 10
ULTIMOS_RATIO = Decimal("0.15")
VENDIENDO_RAPIDO_RATIO = Decimal("0.60")

AGOTADO = "agotado"
ULTIMOS = "ultimos"
RAPIDO = "rapido"
DISPONIBLE = "disponible"


def _nivel(cupo: int, vendidas: int) -> str:
    disponibles = max(cupo - vendidas, 0)
    if cupo == 0 or disponibles == 0:
        return AGOTADO
    if disponibles <= max(ULTIMOS_MIN_SILLAS, int(cupo * ULTIMOS_RATIO)):
        return ULTIMOS
    if Decimal(vendidas) / Decimal(cupo) >= VENDIENDO_RAPIDO_RATIO:
        return RAPIDO
    return DISPONIBLE


def _porcentaje(cupo: int, vendidas: int) -> int:
    if cupo == 0:
        return 100
    return min(100, round(vendidas * 100 / cupo))


@dataclass(frozen=True)
class LocalidadVM:
    localidad: Localidad

    @property
    def id(self) -> int:
        return self.localidad.id

    @property
    def nombre(self) -> str:
        return self.localidad.nombre

    @property
    def precio(self) -> Decimal:
        return self.localidad.precio

    @property
    def disponibles(self) -> int:
        return max(self.localidad.cupo - self.localidad.vendidas, 0)

    @property
    def porcentaje_vendido(self) -> int:
        return _porcentaje(self.localidad.cupo, self.localidad.vendidas)

    @property
    def nivel(self) -> str:
        return _nivel(self.localidad.cupo, self.localidad.vendidas)

    @property
    def es_premium(self) -> bool:
        return self.localidad.tipo in (Localidad.Tipo.VIP, Localidad.Tipo.PALCO)


class EventoCardVM:
    """Todo lo que necesita una Event Card, calculado una sola vez."""

    def __init__(self, evento: Evento):
        self.evento = evento

    @cached_property
    def localidades(self) -> list[LocalidadVM]:
        return [LocalidadVM(loc) for loc in self.evento.localidades.all()]

    @cached_property
    def cupo_total(self) -> int:
        return sum(l.localidad.cupo for l in self.localidades)

    @cached_property
    def vendidas_total(self) -> int:
        return sum(l.localidad.vendidas for l in self.localidades)

    @cached_property
    def porcentaje_vendido(self) -> int:
        return _porcentaje(self.cupo_total, self.vendidas_total)

    @cached_property
    def precio_desde(self) -> Decimal | None:
        con_cupo = [l.precio for l in self.localidades if l.disponibles > 0]
        candidatos = con_cupo or [l.precio for l in self.localidades]
        return min(candidatos) if candidatos else None

    @cached_property
    def zona_critica(self) -> LocalidadVM | None:
        """Localidad en 'últimos asientos' (la de menos sillas libres)."""
        criticas = [l for l in self.localidades if l.nivel == ULTIMOS]
        return min(criticas, key=lambda l: l.disponibles) if criticas else None

    @cached_property
    def nivel(self) -> str:
        """Nivel del evento. Se muestra '¡Últimos asientos!' si CUALQUIER
        zona está crítica (la tarjeta nombra cuál), para no exagerar la
        escasez de todo el evento."""
        if not self.localidades or all(l.nivel == AGOTADO for l in self.localidades):
            return AGOTADO
        if self.zona_critica:
            return ULTIMOS
        return _nivel(self.cupo_total, self.vendidas_total)

    @property
    def agotado(self) -> bool:
        return self.nivel == AGOTADO

    def como_json(self) -> dict:
        """Payload mínimo que consume el checkout (Alpine store)."""
        e = self.evento
        return {
            "id": e.id,
            "titulo": e.titulo,
            "lugar": e.lugar,
            "imagen": e.imagen_url,
            "fecha": e.fecha_evento.isoformat(),
            "tipo_recinto": e.tipo_recinto,
            "localidades": [
                {
                    "id": l.id,
                    "nombre": l.nombre,
                    "precio": str(l.precio),
                    "disponibles": l.disponibles,
                    "nivel": l.nivel,
                    "premium": l.es_premium,
                }
                for l in self.localidades
            ],
        }
