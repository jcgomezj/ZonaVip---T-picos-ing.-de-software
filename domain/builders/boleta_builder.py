"""
Builder de la entidad más compleja del sistema: la Boleta.

Por qué Builder y no `Boleta.objects.create(...)` directo:
la construcción de una boleta tiene varios pasos condicionales que deben
ejecutarse en orden y de forma atómica antes de que el objeto se considere
válido (usuario, evento, localidad con cupo, precio derivado de la
localidad, código QR, marca de tiempo de reserva). El Builder garantiza
que `build()` nunca entregue un objeto a medio construir: o lanza una
excepción de dominio, o entrega un `BoletaData` completo y consistente.

Este módulo vive en `domain/` porque no depende de Django ni del ORM:
solo recibe un objeto `localidad` con el que interactúa a través de un
contrato mínimo (`.id`, `.nombre`, `.precio`, `.hay_cupo()`), lo que lo
hace trivialmente testeable con dobles de prueba (ver tests/).
"""

import uuid
from dataclasses import dataclass
from datetime import datetime, timezone as dt_timezone
from typing import Optional

from domain.exceptions import ConflictoEstadoError, ValidacionNegocioError


class BoletaInvalidaError(ValidacionNegocioError):
    """Datos insuficientes o inconsistentes para construir la boleta."""


class SinCupoError(ConflictoEstadoError):
    """La localidad elegida no tiene cupo disponible."""


@dataclass
class BoletaData:
    usuario_id: Optional[int] = None
    evento_id: Optional[int] = None
    localidad_id: Optional[int] = None
    codigo_qr: Optional[str] = None
    estado: str = "RESERVADA"
    reservada_en: Optional[datetime] = None
    precio: Optional[float] = None


class BoletaBuilder:
    """
    Uso:

        boleta_data = (
            BoletaBuilder()
            .para_usuario(usuario.id)
            .para_evento(evento.id)
            .en_localidad(localidad)
            .generar_codigo_qr()
            .marcar_reservada_ahora()
            .build()
        )
    """

    def __init__(self):
        self._data = BoletaData()

    def para_usuario(self, usuario_id: int) -> "BoletaBuilder":
        if not usuario_id:
            raise BoletaInvalidaError("La boleta requiere un usuario válido.")
        self._data.usuario_id = usuario_id
        return self

    def para_evento(self, evento_id: int) -> "BoletaBuilder":
        if not evento_id:
            raise BoletaInvalidaError("La boleta requiere un evento válido.")
        self._data.evento_id = evento_id
        return self

    def en_localidad(self, localidad) -> "BoletaBuilder":
        if not localidad.hay_cupo():
            raise SinCupoError(
                f"La localidad '{localidad.nombre}' no tiene cupo disponible."
            )
        self._data.localidad_id = localidad.id
        self._data.precio = localidad.precio
        return self

    def generar_codigo_qr(self) -> "BoletaBuilder":
        self._data.codigo_qr = str(uuid.uuid4())
        return self

    def marcar_reservada_ahora(self) -> "BoletaBuilder":
        # Se usa UTC explícito (con tzinfo) en vez de `datetime.now()` naive:
        # el dominio sigue sin depender de Django, pero el dato ya es
        # timezone-aware, como exige `USE_TZ=True` en el proyecto.
        self._data.reservada_en = datetime.now(dt_timezone.utc)
        self._data.estado = "RESERVADA"
        return self

    def build(self) -> BoletaData:
        if not self._data.usuario_id:
            raise BoletaInvalidaError("Falta asociar un usuario a la boleta.")
        if not self._data.evento_id:
            raise BoletaInvalidaError("Falta asociar un evento a la boleta.")
        if not self._data.localidad_id:
            raise BoletaInvalidaError("Falta asociar una localidad a la boleta.")
        if self._data.precio is None:
            raise BoletaInvalidaError("No fue posible determinar el precio de la boleta.")
        if not self._data.codigo_qr:
            # Si el Service olvidó pedirlo explícitamente, el Builder
            # garantiza consistencia igual: nunca sale una boleta sin QR.
            self.generar_codigo_qr()
        if not self._data.reservada_en:
            self.marcar_reservada_ahora()

        return self._data
