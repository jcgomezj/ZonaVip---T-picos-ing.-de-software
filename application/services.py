"""
Capa de aplicación (Service Layer).

Regla de oro de este proyecto: las Views y los Serializers NUNCA contienen
lógica de negocio. Cada flujo principal está orquestado por una única clase
aquí, con una única responsabilidad (SRP):

- ReservaBoletaService   -> reservar una boleta para un usuario
- CancelarBoletaService  -> cancelar una boleta y liberar el cupo
- CrearEventoService     -> un organizador crea un evento (BORRADOR)
- PublicarEventoService  -> un organizador publica un evento (BORRADOR -> PUBLICADO)

Los Repositorios aíslan el ORM de Django del resto de la capa de aplicación:
si mañana cambia el motor de persistencia, solo cambian estas clases.
"""

from dataclasses import dataclass
from datetime import datetime
from typing import Optional

from django.db import transaction
from django.utils import timezone

from apps.boletas.models import Boleta
from apps.eventos.models import Evento, Localidad, Organizador
from domain.builders.boleta_builder import BoletaBuilder
from domain.exceptions import (
    ConflictoEstadoError,
    RecursoNoEncontradoError,
    ValidacionNegocioError,
)
from infra.factories.notificador_factory import NotificadorFactory
from infra.notificadores.correo_compra import enviar_correo_compra


# ---------------------------------------------------------------------------
# DTOs de entrada: desacoplan el Service de `request.data` / los Serializers.
# ---------------------------------------------------------------------------


@dataclass
class ReservaBoletaDTO:
    usuario_id: int
    evento_id: int
    localidad_id: int


@dataclass
class CompraBoletasDTO:
    usuario_id: int
    evento_id: int
    localidad_id: int
    cantidad: int


@dataclass
class CrearEventoDTO:
    organizador_id: int
    categoria_id: int
    titulo: str
    lugar: str
    fecha_evento: datetime
    descripcion: str = ""


# ---------------------------------------------------------------------------
# Repositorios: única frontera contra el ORM.
# ---------------------------------------------------------------------------


class LocalidadRepository:
    def obtener_por_id(self, localidad_id: int) -> Localidad:
        try:
            return Localidad.objects.select_for_update().get(id=localidad_id)
        except Localidad.DoesNotExist:
            raise RecursoNoEncontradoError(f"La localidad {localidad_id} no existe.")


class EventoRepository:
    def obtener_por_id(self, evento_id: int) -> Evento:
        try:
            return Evento.objects.get(id=evento_id)
        except Evento.DoesNotExist:
            raise RecursoNoEncontradoError(f"El evento {evento_id} no existe.")

    def guardar(self, evento: Evento) -> Evento:
        evento.save()
        return evento


class BoletaRepository:
    def guardar(self, boleta_data) -> Boleta:
        return Boleta.objects.create(
            usuario_id=boleta_data.usuario_id,
            evento_id=boleta_data.evento_id,
            localidad_id=boleta_data.localidad_id,
            codigo_qr=boleta_data.codigo_qr,
            precio=boleta_data.precio,
            estado=boleta_data.estado,
            reservada_en=boleta_data.reservada_en,
        )

    def obtener_por_id(self, boleta_id: int) -> Boleta:
        try:
            return Boleta.objects.select_for_update().get(id=boleta_id)
        except Boleta.DoesNotExist:
            raise RecursoNoEncontradoError(f"La boleta {boleta_id} no existe.")


# ---------------------------------------------------------------------------
# Servicios
# ---------------------------------------------------------------------------


class ReservaBoletaService:
    """Flujo: un usuario reserva una boleta en una localidad de un evento."""

    def __init__(
        self,
        localidad_repo: Optional[LocalidadRepository] = None,
        boleta_repo: Optional[BoletaRepository] = None,
    ):
        self._localidad_repo = localidad_repo or LocalidadRepository()
        self._boleta_repo = boleta_repo or BoletaRepository()
        self._notificador = NotificadorFactory.crear()

    @transaction.atomic
    def ejecutar(self, datos: ReservaBoletaDTO) -> Boleta:
        localidad = self._localidad_repo.obtener_por_id(datos.localidad_id)

        boleta_data = (
            BoletaBuilder()
            .para_usuario(datos.usuario_id)
            .para_evento(datos.evento_id)
            .en_localidad(localidad)
            .generar_codigo_qr()
            .marcar_reservada_ahora()
            .build()
        )

        boleta = self._boleta_repo.guardar(boleta_data)

        localidad.vendidas += 1
        localidad.save(update_fields=["vendidas"])

        self._notificador.enviar_confirmacion_boleta(boleta)

        return boleta


class CompraBoletasService:
    """Flujo: un usuario autenticado compra N boletas de una misma localidad.

    Todo ocurre en una transacción: o se emiten las N boletas (estado PAGADA)
    y se descuenta el cupo, o no se emite ninguna. El correo de confirmación
    sale solo cuando la transacción hizo commit.
    """

    MAX_BOLETAS = 8

    def __init__(
        self,
        localidad_repo: Optional[LocalidadRepository] = None,
        boleta_repo: Optional[BoletaRepository] = None,
    ):
        self._localidad_repo = localidad_repo or LocalidadRepository()
        self._boleta_repo = boleta_repo or BoletaRepository()

    @transaction.atomic
    def ejecutar(self, datos: CompraBoletasDTO) -> list[Boleta]:
        if not 1 <= datos.cantidad <= self.MAX_BOLETAS:
            raise ValidacionNegocioError(
                f"Puedes comprar entre 1 y {self.MAX_BOLETAS} boletas por transacción."
            )

        localidad = self._localidad_repo.obtener_por_id(datos.localidad_id)
        if localidad.evento_id != datos.evento_id:
            raise ValidacionNegocioError("La localidad no pertenece al evento indicado.")
        if localidad.evento.estado != Evento.Estado.PUBLICADO:
            raise ConflictoEstadoError("El evento no está disponible para la venta.")
        if localidad.cupo - localidad.vendidas < datos.cantidad:
            raise ConflictoEstadoError(
                f"Solo quedan {localidad.cupo - localidad.vendidas} boletas en "
                f"'{localidad.nombre}'."
            )

        boletas = []
        for _ in range(datos.cantidad):
            boleta_data = (
                BoletaBuilder()
                .para_usuario(datos.usuario_id)
                .para_evento(datos.evento_id)
                .en_localidad(localidad)
                .generar_codigo_qr()
                .marcar_reservada_ahora()
                .build()
            )
            boleta_data.estado = Boleta.Estado.PAGADA
            boletas.append(self._boleta_repo.guardar(boleta_data))

        localidad.vendidas += datos.cantidad
        localidad.save(update_fields=["vendidas"])

        ids = [b.id for b in boletas]

        def _notificar():
            # Se recargan con select_related para armar el correo sin N+1.
            cargadas = list(
                Boleta.objects.filter(id__in=ids)
                .select_related("usuario", "evento", "localidad")
                .order_by("id")
            )
            enviar_correo_compra(cargadas[0].usuario, cargadas)

        transaction.on_commit(_notificar)
        return boletas


class CancelarBoletaService:
    """Flujo: el dueño de una boleta la cancela y su cupo vuelve a la localidad."""

    def __init__(self, boleta_repo: Optional[BoletaRepository] = None):
        self._boleta_repo = boleta_repo or BoletaRepository()

    @transaction.atomic
    def ejecutar(self, boleta_id: int, usuario_id: int) -> Boleta:
        boleta = self._boleta_repo.obtener_por_id(boleta_id)

        if boleta.usuario_id != usuario_id:
            raise ConflictoEstadoError("No puedes cancelar una boleta de otro usuario.")
        if boleta.estado == Boleta.Estado.CANCELADA:
            raise ConflictoEstadoError("La boleta ya se encuentra cancelada.")

        boleta.estado = Boleta.Estado.CANCELADA
        boleta.save(update_fields=["estado"])

        localidad = boleta.localidad
        localidad.vendidas = max(0, localidad.vendidas - 1)
        localidad.save(update_fields=["vendidas"])

        return boleta


class CrearEventoService:
    """Flujo: un organizador crea un evento nuevo, siempre en estado BORRADOR."""

    def __init__(self, evento_repo: Optional[EventoRepository] = None):
        self._evento_repo = evento_repo or EventoRepository()

    def ejecutar(self, datos: CrearEventoDTO) -> Evento:
        if not datos.titulo or not datos.titulo.strip():
            raise ValidacionNegocioError("El evento requiere un título.")
        if datos.fecha_evento <= timezone.now():
            raise ValidacionNegocioError("La fecha del evento debe ser futura.")

        try:
            organizador = Organizador.objects.get(id=datos.organizador_id)
        except Organizador.DoesNotExist:
            raise RecursoNoEncontradoError(
                f"El organizador {datos.organizador_id} no existe."
            )

        evento = Evento(
            organizador=organizador,
            categoria_id=datos.categoria_id,
            titulo=datos.titulo,
            descripcion=datos.descripcion,
            lugar=datos.lugar,
            fecha_evento=datos.fecha_evento,
            estado=Evento.Estado.BORRADOR,
        )
        return self._evento_repo.guardar(evento)


class PublicarEventoService:
    """Flujo: BORRADOR -> PUBLICADO. Exige al menos una localidad configurada."""

    def __init__(self, evento_repo: Optional[EventoRepository] = None):
        self._evento_repo = evento_repo or EventoRepository()

    def ejecutar(self, evento_id: int, organizador_id: int) -> Evento:
        evento = self._evento_repo.obtener_por_id(evento_id)

        if evento.organizador_id != organizador_id:
            raise ConflictoEstadoError("No puedes publicar un evento de otro organizador.")
        if evento.estado != Evento.Estado.BORRADOR:
            raise ConflictoEstadoError(
                f"El evento ya está en estado '{evento.estado}' y no puede publicarse de nuevo."
            )
        if not evento.localidades.exists():
            raise ValidacionNegocioError(
                "El evento necesita al menos una localidad antes de publicarse."
            )

        evento.estado = Evento.Estado.PUBLICADO
        return self._evento_repo.guardar(evento)
