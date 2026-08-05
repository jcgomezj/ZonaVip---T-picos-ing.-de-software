

import uuid
from dataclasses import dataclass, field
from datetime import datetime
from typing import Optional


class BoletaInvalidaError(Exception):
    
    pass


@dataclass
class BoletaData:

    usuario_id: Optional[int] = None
    localidad_id: Optional[int] = None
    evento_id: Optional[int] = None
    codigo_qr: Optional[str] = None
    estado: str = "PENDIENTE"
    reservada_en: Optional[datetime] = None
    precio: Optional[float] = None


class BoletaBuilder:
    """

        boleta = (
            BoletaBuilder()
            .para_usuario(usuario.id)
            .en_localidad(localidad)
            .para_evento(evento.id)
            .generar_codigo_qr()
            .build()
        )
    """

    def __init__(self):
        self._data = BoletaData()
        self._localidad = None  # referencia al objeto Localidad (para validar cupo)

    def para_usuario(self, usuario_id: int) -> "BoletaBuilder":
        if not usuario_id:
            raise BoletaInvalidaError("La boleta requiere un usuario válido.")
        self._data.usuario_id = usuario_id
        return self

    def para_evento(self, evento_id: int) -> "BoletaBuilder":
        self._data.evento_id = evento_id
        return self

    def en_localidad(self, localidad) -> "BoletaBuilder":

        if not localidad.hay_cupo():
            raise BoletaInvalidaError(
                f"La localidad '{localidad.nombre}' no tiene cupo disponible."
            )
        self._localidad = localidad
        self._data.localidad_id = localidad.id
        self._data.precio = localidad.precio
        return self

    def generar_codigo_qr(self) -> "BoletaBuilder":
        self._data.codigo_qr = str(uuid.uuid4())
        return self

    def marcar_reservada_ahora(self) -> "BoletaBuilder":
        self._data.reservada_en = datetime.now()
        self._data.estado = "RESERVADA"
        return self

    def build(self) -> BoletaData:
 
        if not self._data.usuario_id:
            raise BoletaInvalidaError("Falta asociar un usuario a la boleta.")
        if not self._data.localidad_id:
            raise BoletaInvalidaError("Falta asociar una localidad a la boleta.")
        if not self._data.codigo_qr:
            # Si el service se olvidó de pedirlo, lo generamos igual:
            # el Builder garantiza consistencia aunque el orquestador falle.
            self.generar_codigo_qr()
        if self._data.precio is None:
            raise BoletaInvalidaError("No fue posible determinar el precio.")
        if not self._data.reservada_en:
            self.marcar_reservada_ahora()

        return self._data
