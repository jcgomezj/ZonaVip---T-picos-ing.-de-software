"""
Capa de aplicación (Service Layer).

Las Views y Serializers NUNCA contienen lógica de negocio. Cada flujo está
orquestado por una clase con una única responsabilidad (SRP):

- ReservaBoletaService   -> reservar (retiene cupo hasta que expira)
- PagarReservaService    -> pagar una reserva (RESERVADA -> PAGADA)
- CompraBoletasService   -> comprar N boletas con pago e idempotencia
- CancelarBoletaService  -> cancelar una boleta y liberar cupo (reembolsa)
- ValidarBoletaService   -> check-in en el ingreso (PAGADA -> USADA)
- ExpirarReservasService -> liberar cupo de reservas sin pagar vencidas
- CrearEventoService / PublicarEventoService
- CancelarEventoService  -> cancelar evento, boletas y notificar (Celery)

Concurrencia: orden de bloqueo fijo evento -> localidad (-> boleta) y
contadores de cupo con UPDATE atómicos (`F()`), nunca leer-modificar-escribir.
"""

from __future__ import annotations

import logging
from collections import Counter
from dataclasses import dataclass
from datetime import datetime, timedelta
from decimal import Decimal
from typing import Optional

from django.conf import settings
from django.db import IntegrityError, transaction
from django.db.models import F, Value
from django.db.models.functions import Greatest
from django.utils import timezone

from apps.boletas.models import Boleta, Pago
from apps.eventos.models import Evento, Localidad, Organizador
from domain.builders.boleta_builder import BoletaBuilder
from domain.exceptions import (
    BoletaYaUsadaError,
    ConflictoEstadoError,
    PagoRechazadoError,
    PermisoDenegadoError,
    RecursoNoEncontradoError,
    ValidacionNegocioError,
)
from infra.factories.notificador_factory import NotificadorFactory
from infra.notificadores.correo_compra import enviar_correo_compra
from infra.pagos.factory import PasarelaPagoFactory
from infra.pagos.pasarela_simulada import METODOS_VALIDOS
from infra.qr import decodificar_payload

logger = logging.getLogger(__name__)


# --------------------------- DTOs de entrada ---------------------------


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
    metodo_pago: str = "TARJETA"
    token_pago: str = "tok_ok"
    idempotency_key: Optional[str] = None


@dataclass
class PagarReservaDTO:
    boleta_id: int
    usuario_id: int
    metodo_pago: str = "TARJETA"
    token_pago: str = "tok_ok"
    idempotency_key: Optional[str] = None


@dataclass
class CrearEventoDTO:
    organizador_id: int
    categoria_id: int
    titulo: str
    lugar: str
    fecha_evento: datetime
    descripcion: str = ""


@dataclass
class ValidarBoletaDTO:
    codigo: str
    validador_id: int
    es_staff: bool = False
    evento_id: Optional[int] = None


@dataclass
class CancelarEventoDTO:
    evento_id: int
    usuario_id: int
    es_staff: bool = False
    motivo: str = ""


# ----------------------------- Resultados ------------------------------


@dataclass
class ResultadoCompra:
    boletas: list
    pago: Pago
    repetida: bool = False


@dataclass
class ResultadoCheckin:
    boleta: Boleta
    tipo_qr: str


@dataclass
class ResultadoCancelacionEvento:
    evento: Evento
    boletas_canceladas: int
    reembolsos: int
    monto_reembolsado: Decimal


# ---------------------------- Repositorios -----------------------------


class LocalidadRepository:
    def obtener_por_id(self, localidad_id: int) -> Localidad:
        try:
            return Localidad.objects.select_for_update().get(id=localidad_id)
        except Localidad.DoesNotExist:
            raise RecursoNoEncontradoError(f"La localidad {localidad_id} no existe.")

    def ajustar_vendidas(self, localidad_id: int, delta: int) -> None:
        """UPDATE atómico; nunca baja de 0 (el CheckConstraint cubre el cupo)."""
        Localidad.objects.filter(id=localidad_id).update(
            vendidas=Greatest(F("vendidas") + delta, Value(0))
        )


class EventoRepository:
    def obtener_por_id(self, evento_id: int) -> Evento:
        try:
            return Evento.objects.get(id=evento_id)
        except Evento.DoesNotExist:
            raise RecursoNoEncontradoError(f"El evento {evento_id} no existe.")

    def obtener_bloqueado(self, evento_id: int) -> Evento:
        try:
            return (
                Evento.objects.select_for_update(of=("self",))
                .select_related("organizador")
                .get(id=evento_id)
            )
        except Evento.DoesNotExist:
            raise RecursoNoEncontradoError(f"El evento {evento_id} no existe.")

    def guardar(self, evento: Evento) -> Evento:
        evento.save()
        return evento


class BoletaRepository:
    def guardar(self, boleta_data, *, estado: Optional[str] = None,
                pago: Optional[Pago] = None, expira_en: Optional[datetime] = None) -> Boleta:
        return Boleta.objects.create(
            usuario_id=boleta_data.usuario_id,
            evento_id=boleta_data.evento_id,
            localidad_id=boleta_data.localidad_id,
            pago=pago,
            codigo_qr=boleta_data.codigo_qr,
            precio=boleta_data.precio,
            estado=estado or boleta_data.estado,
            reservada_en=boleta_data.reservada_en,
            expira_en=expira_en,
        )

    def obtener_por_id(self, boleta_id: int) -> Boleta:
        try:
            return (
                Boleta.objects.select_for_update(of=("self",))
                .select_related("evento", "pago")
                .get(id=boleta_id)
            )
        except Boleta.DoesNotExist:
            raise RecursoNoEncontradoError(f"La boleta {boleta_id} no existe.")

    def obtener_por_codigo(self, codigo: str) -> Boleta:
        try:
            return (
                Boleta.objects.select_for_update(of=("self",))
                .select_related("evento", "evento__organizador", "localidad", "usuario")
                .get(codigo_qr=codigo)
            )
        except Boleta.DoesNotExist:
            raise RecursoNoEncontradoError(
                "No existe ninguna boleta con ese código.", codigo="boleta_inexistente"
            )


class PagoRepository:
    def por_clave(self, usuario_id: int, clave: str) -> Optional[Pago]:
        return Pago.objects.filter(usuario_id=usuario_id, idempotency_key=clave).first()


# --------------------------- Reglas compartidas ------------------------


def _bloquear_evento_y_localidad(evento_id: int, localidad_id: int) -> tuple[Evento, Localidad]:
    """Bloquea evento -> localidad y valida pertenencia y que el evento esté a
    la venta. Bloquear el evento serializa compra vs. cancelación de evento."""
    try:
        evento = Evento.objects.select_for_update().get(id=evento_id)
    except Evento.DoesNotExist:
        raise ValidacionNegocioError("La localidad no pertenece al evento indicado.")

    localidad = LocalidadRepository().obtener_por_id(localidad_id)
    if localidad.evento_id != evento.id:
        raise ValidacionNegocioError("La localidad no pertenece al evento indicado.")
    if evento.estado != Evento.Estado.PUBLICADO:
        raise ConflictoEstadoError(
            "El evento no está disponible para la venta.", codigo="evento_no_disponible"
        )
    if evento.fecha_evento <= timezone.now():
        raise ConflictoEstadoError("El evento ya ocurrió.", codigo="evento_finalizado")
    return evento, localidad


def _validar_metodo(metodo: str) -> str:
    metodo = (metodo or "TARJETA").upper()
    if metodo not in METODOS_VALIDOS:
        raise ValidacionNegocioError(
            f"Método de pago no soportado. Usa uno de: {', '.join(METODOS_VALIDOS)}.",
            codigo="metodo_pago_invalido",
        )
    return metodo


def _encolar_correo_compra(ids: list[int]) -> None:
    def _notificar():
        cargadas = list(
            Boleta.objects.filter(id__in=ids)
            .select_related("usuario", "evento", "localidad")
            .order_by("id")
        )
        if cargadas:
            enviar_correo_compra(cargadas[0].usuario, cargadas)

    transaction.on_commit(_notificar)


# ------------------------------ Servicios ------------------------------


class ReservaBoletaService:
    """Reserva una boleta; retiene el cupo `RESERVA_TTL_MINUTOS`."""

    def __init__(self, localidad_repo: Optional[LocalidadRepository] = None,
                 boleta_repo: Optional[BoletaRepository] = None):
        self._localidad_repo = localidad_repo or LocalidadRepository()
        self._boleta_repo = boleta_repo or BoletaRepository()
        self._notificador = NotificadorFactory.crear()

    @transaction.atomic
    def ejecutar(self, datos: ReservaBoletaDTO) -> Boleta:
        _, localidad = _bloquear_evento_y_localidad(datos.evento_id, datos.localidad_id)
        boleta_data = (
            BoletaBuilder()
            .para_usuario(datos.usuario_id)
            .para_evento(datos.evento_id)
            .en_localidad(localidad)
            .generar_codigo_qr()
            .marcar_reservada_ahora()
            .build()
        )
        expira_en = boleta_data.reservada_en + timedelta(minutes=settings.RESERVA_TTL_MINUTOS)
        boleta = self._boleta_repo.guardar(boleta_data, expira_en=expira_en)
        self._localidad_repo.ajustar_vendidas(localidad.id, +1)
        transaction.on_commit(lambda: self._notificador.enviar_confirmacion_boleta(boleta))
        return boleta


class CompraBoletasService:
    """Compra N boletas de una localidad: cobra y emite todo en UNA transacción.

    Idempotencia: misma `idempotency_key` del mismo usuario => NO se cobra otra
    vez, se devuelve el resultado original. Clave reutilizada con otra
    solicitud => 400."""

    MAX_BOLETAS = 8

    def __init__(self, localidad_repo=None, boleta_repo=None, pago_repo=None, pasarela=None):
        self._localidad_repo = localidad_repo or LocalidadRepository()
        self._boleta_repo = boleta_repo or BoletaRepository()
        self._pago_repo = pago_repo or PagoRepository()
        self._pasarela = pasarela or PasarelaPagoFactory.crear()

    @transaction.atomic
    def ejecutar(self, datos: CompraBoletasDTO) -> ResultadoCompra:
        if not 1 <= datos.cantidad <= self.MAX_BOLETAS:
            raise ValidacionNegocioError(
                f"Puedes comprar entre 1 y {self.MAX_BOLETAS} boletas por transacción."
            )
        metodo = _validar_metodo(datos.metodo_pago)
        evento, localidad = _bloquear_evento_y_localidad(datos.evento_id, datos.localidad_id)

        if datos.idempotency_key:
            previo = self._pago_repo.por_clave(datos.usuario_id, datos.idempotency_key)
            if previo:
                return self._repetir(previo, datos)

        disponibles = localidad.cupo - localidad.vendidas
        if disponibles < datos.cantidad:
            raise ConflictoEstadoError(
                f"Solo quedan {disponibles} boletas en '{localidad.nombre}'.", codigo="sin_cupo"
            )

        monto = Decimal(localidad.precio) * datos.cantidad
        cobro = self._pasarela.cobrar(monto, metodo, datos.token_pago)
        if not cobro.aprobado:
            raise PagoRechazadoError(cobro.motivo or "El pago fue rechazado.")

        try:
            with transaction.atomic():
                pago = Pago.objects.create(
                    usuario_id=datos.usuario_id, evento=evento, localidad=localidad,
                    cantidad=datos.cantidad, monto=monto, metodo=metodo,
                    referencia=cobro.referencia,
                    idempotency_key=datos.idempotency_key or None,
                )
        except IntegrityError:
            self._pasarela.reembolsar(cobro.referencia, monto)
            raise ConflictoEstadoError(
                "Esta solicitud ya se está procesando. Revisa tus boletas.",
                codigo="solicitud_duplicada",
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
            boletas.append(self._boleta_repo.guardar(boleta_data, estado=Boleta.Estado.PAGADA, pago=pago))

        self._localidad_repo.ajustar_vendidas(localidad.id, datos.cantidad)
        _encolar_correo_compra([b.id for b in boletas])
        return ResultadoCompra(boletas=boletas, pago=pago)

    @staticmethod
    def _repetir(previo: Pago, datos: CompraBoletasDTO) -> ResultadoCompra:
        if (previo.evento_id != datos.evento_id or previo.localidad_id != datos.localidad_id
                or previo.cantidad != datos.cantidad):
            raise ValidacionNegocioError(
                "Esta Idempotency-Key ya se usó con una solicitud distinta.",
                codigo="idempotencia_conflicto",
            )
        return ResultadoCompra(boletas=list(previo.boletas.order_by("id")), pago=previo, repetida=True)


class PagarReservaService:
    """El dueño de una reserva vigente la paga (RESERVADA -> PAGADA)."""

    def __init__(self, boleta_repo=None, pasarela=None):
        self._boleta_repo = boleta_repo or BoletaRepository()
        self._pasarela = pasarela or PasarelaPagoFactory.crear()

    @transaction.atomic
    def ejecutar(self, datos: PagarReservaDTO) -> ResultadoCompra:
        metodo = _validar_metodo(datos.metodo_pago)
        boleta = self._boleta_repo.obtener_por_id(datos.boleta_id)

        if boleta.usuario_id != datos.usuario_id:
            raise PermisoDenegadoError("No puedes pagar una boleta de otro usuario.")

        if (boleta.estado == Boleta.Estado.PAGADA and datos.idempotency_key and boleta.pago
                and boleta.pago.idempotency_key == datos.idempotency_key):
            return ResultadoCompra(boletas=[boleta], pago=boleta.pago, repetida=True)

        if boleta.estado != Boleta.Estado.RESERVADA:
            raise ConflictoEstadoError(
                f"La boleta está en estado '{boleta.estado}' y no puede pagarse.",
                codigo="estado_invalido",
            )
        if boleta.expira_en and boleta.expira_en <= timezone.now():
            raise ConflictoEstadoError(
                "La reserva venció. Vuelve a reservar para pagar.", codigo="reserva_vencida"
            )
        if boleta.evento.estado != Evento.Estado.PUBLICADO:
            raise ConflictoEstadoError("El evento no está disponible.", codigo="evento_no_disponible")

        monto = Decimal(boleta.precio)
        cobro = self._pasarela.cobrar(monto, metodo, datos.token_pago)
        if not cobro.aprobado:
            raise PagoRechazadoError(cobro.motivo or "El pago fue rechazado.")

        pago = Pago.objects.create(
            usuario_id=datos.usuario_id, evento_id=boleta.evento_id,
            localidad_id=boleta.localidad_id, cantidad=1, monto=monto, metodo=metodo,
            referencia=cobro.referencia, idempotency_key=datos.idempotency_key or None,
        )
        boleta.estado = Boleta.Estado.PAGADA
        boleta.pago = pago
        boleta.expira_en = None
        boleta.save(update_fields=["estado", "pago", "expira_en"])
        _encolar_correo_compra([boleta.id])
        return ResultadoCompra(boletas=[boleta], pago=pago)


class CancelarBoletaService:
    """El dueño cancela su boleta; el cupo vuelve y lo pagado se reembolsa."""

    def __init__(self, boleta_repo=None, localidad_repo=None, pasarela=None):
        self._boleta_repo = boleta_repo or BoletaRepository()
        self._localidad_repo = localidad_repo or LocalidadRepository()
        self._pasarela = pasarela or PasarelaPagoFactory.crear()

    @transaction.atomic
    def ejecutar(self, boleta_id: int, usuario_id: int) -> Boleta:
        boleta = self._boleta_repo.obtener_por_id(boleta_id)

        if boleta.usuario_id != usuario_id:
            raise PermisoDenegadoError("No puedes cancelar una boleta de otro usuario.")
        if boleta.estado == Boleta.Estado.CANCELADA:
            raise ConflictoEstadoError("La boleta ya se encuentra cancelada.")
        if boleta.estado == Boleta.Estado.USADA:
            raise ConflictoEstadoError("La boleta ya fue usada y no puede cancelarse.", codigo="ya_usada")
        if boleta.evento.fecha_evento <= timezone.now():
            raise ConflictoEstadoError("El evento ya ocurrió.", codigo="evento_finalizado")

        estaba_pagada = boleta.estado == Boleta.Estado.PAGADA
        boleta.estado = Boleta.Estado.CANCELADA
        boleta.motivo_cancelacion = Boleta.MotivoCancelacion.USUARIO
        boleta.expira_en = None
        boleta.save(update_fields=["estado", "motivo_cancelacion", "expira_en"])
        self._localidad_repo.ajustar_vendidas(boleta.localidad_id, -1)

        if estaba_pagada and boleta.pago_id:
            pago = boleta.pago
            self._pasarela.reembolsar(pago.referencia, Decimal(boleta.precio))
            if not pago.boletas.filter(estado__in=[Boleta.Estado.PAGADA, Boleta.Estado.USADA]).exists():
                pago.estado = Pago.Estado.REEMBOLSADO
                pago.save(update_fields=["estado"])
        return boleta


class ValidarBoletaService:
    """Check-in: PAGADA -> USADA. Valida staff u organizador DEL evento. La fila
    se bloquea: dos lectores con el mismo QR no pueden dejar pasar a dos."""

    def __init__(self, boleta_repo: Optional[BoletaRepository] = None):
        self._boleta_repo = boleta_repo or BoletaRepository()

    @transaction.atomic
    def ejecutar(self, datos: ValidarBoletaDTO) -> ResultadoCheckin:
        try:
            codigo, tipo_qr = decodificar_payload(datos.codigo)
        except ValueError as exc:
            raise ValidacionNegocioError(str(exc), codigo="qr_invalido")

        if settings.CHECKIN_EXIGIR_QR_DINAMICO and tipo_qr != "dinamico":
            raise ValidacionNegocioError(
                "Solo se aceptan QR dinámicos (los del perfil del asistente).",
                codigo="qr_no_dinamico",
            )

        boleta = self._boleta_repo.obtener_por_codigo(codigo)
        evento = boleta.evento

        if not (datos.es_staff or evento.organizador.usuario_id == datos.validador_id):
            raise PermisoDenegadoError("No tienes permiso para validar boletas de este evento.")
        if datos.evento_id and boleta.evento_id != datos.evento_id:
            raise ConflictoEstadoError(
                f"Esta boleta es para otro evento: {evento.titulo}.", codigo="otro_evento"
            )
        if boleta.estado == Boleta.Estado.USADA:
            cuando = timezone.localtime(boleta.usada_en).strftime("%d/%m/%Y %H:%M:%S")
            raise BoletaYaUsadaError(
                f"Esta boleta ya fue usada el {cuando}.", usada_en=boleta.usada_en.isoformat()
            )
        if boleta.estado == Boleta.Estado.CANCELADA:
            raise ConflictoEstadoError("La boleta está cancelada.", codigo="cancelada")
        if boleta.estado == Boleta.Estado.RESERVADA:
            raise ConflictoEstadoError("La boleta está reservada pero no ha sido pagada.", codigo="sin_pago")
        if evento.estado == Evento.Estado.CANCELADO:
            raise ConflictoEstadoError("El evento fue cancelado.", codigo="evento_cancelado")

        ahora = timezone.now()
        if ahora > evento.fecha_evento + timedelta(hours=settings.CHECKIN_CIERRE_HORAS_DESPUES):
            raise ConflictoEstadoError("El ingreso a este evento ya cerró.", codigo="fuera_de_horario")
        apertura = settings.CHECKIN_APERTURA_HORAS_ANTES
        if apertura is not None and ahora < evento.fecha_evento - timedelta(hours=apertura):
            raise ConflictoEstadoError("El ingreso a este evento aún no abre.", codigo="fuera_de_horario")

        boleta.estado = Boleta.Estado.USADA
        boleta.usada_en = ahora
        boleta.validada_por_id = datos.validador_id
        boleta.save(update_fields=["estado", "usada_en", "validada_por"])
        return ResultadoCheckin(boleta=boleta, tipo_qr=tipo_qr)


class ExpirarReservasService:
    """Cancela las reservas sin pagar vencidas y devuelve el cupo."""

    def __init__(self, localidad_repo: Optional[LocalidadRepository] = None):
        self._localidad_repo = localidad_repo or LocalidadRepository()

    def ejecutar(self, ahora: Optional[datetime] = None, lote: int = 500) -> int:
        ahora = ahora or timezone.now()
        ids = list(
            Boleta.objects.filter(estado=Boleta.Estado.RESERVADA, expira_en__lt=ahora)
            .order_by("expira_en").values_list("id", flat=True)[:lote]
        )
        expiradas = 0
        for boleta_id in ids:
            with transaction.atomic():
                boleta = (
                    Boleta.objects.select_for_update()
                    .filter(id=boleta_id, estado=Boleta.Estado.RESERVADA, expira_en__lt=ahora)
                    .first()
                )
                if boleta is None:
                    continue
                boleta.estado = Boleta.Estado.CANCELADA
                boleta.motivo_cancelacion = Boleta.MotivoCancelacion.RESERVA_EXPIRADA
                boleta.save(update_fields=["estado", "motivo_cancelacion"])
                self._localidad_repo.ajustar_vendidas(boleta.localidad_id, -1)
                expiradas += 1
        if expiradas:
            logger.info("Reservas expiradas y cupo liberado: %s", expiradas)
        return expiradas


class CrearEventoService:
    """Un organizador crea un evento, siempre en BORRADOR."""

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
            raise RecursoNoEncontradoError(f"El organizador {datos.organizador_id} no existe.")
        evento = Evento(
            organizador=organizador, categoria_id=datos.categoria_id, titulo=datos.titulo,
            descripcion=datos.descripcion, lugar=datos.lugar, fecha_evento=datos.fecha_evento,
            estado=Evento.Estado.BORRADOR,
        )
        return self._evento_repo.guardar(evento)


class PublicarEventoService:
    """BORRADOR -> PUBLICADO. Exige al menos una localidad."""

    def __init__(self, evento_repo: Optional[EventoRepository] = None):
        self._evento_repo = evento_repo or EventoRepository()

    def ejecutar(self, evento_id: int, organizador_id: int) -> Evento:
        evento = self._evento_repo.obtener_por_id(evento_id)
        if evento.organizador_id != organizador_id:
            raise PermisoDenegadoError("No puedes publicar un evento de otro organizador.")
        if evento.estado != Evento.Estado.BORRADOR:
            raise ConflictoEstadoError(
                f"El evento ya está en estado '{evento.estado}' y no puede publicarse de nuevo."
            )
        if not evento.localidades.exists():
            raise ValidacionNegocioError("El evento necesita al menos una localidad antes de publicarse.")
        evento.estado = Evento.Estado.PUBLICADO
        return self._evento_repo.guardar(evento)


class CancelarEventoService:
    """Cancela un evento (organizador o admin) en UNA transacción: evento
    CANCELADO, boletas RESERVADAS/PAGADAS -> CANCELADA, cupo liberado, pagos
    reembolsados (las USADAS se respetan). Al confirmar encola una tarea de
    Celery que avisa por correo; si el broker falla la cancelación no se deshace."""

    def __init__(self, evento_repo=None, localidad_repo=None, pasarela=None):
        self._evento_repo = evento_repo or EventoRepository()
        self._localidad_repo = localidad_repo or LocalidadRepository()
        self._pasarela = pasarela or PasarelaPagoFactory.crear()

    @transaction.atomic
    def ejecutar(self, datos: CancelarEventoDTO) -> ResultadoCancelacionEvento:
        evento = self._evento_repo.obtener_bloqueado(datos.evento_id)

        if not (datos.es_staff or evento.organizador.usuario_id == datos.usuario_id):
            raise PermisoDenegadoError("No puedes cancelar un evento de otro organizador.")
        if evento.estado not in (Evento.Estado.BORRADOR, Evento.Estado.PUBLICADO):
            raise ConflictoEstadoError(
                f"El evento está en estado '{evento.estado}' y no puede cancelarse.",
                codigo="estado_invalido",
            )

        afectadas = list(
            Boleta.objects.select_for_update(of=("self",)).filter(
                evento=evento, estado__in=[Boleta.Estado.RESERVADA, Boleta.Estado.PAGADA]
            )
        )
        pagadas = [b for b in afectadas if b.estado == Boleta.Estado.PAGADA]
        monto_reembolsado = sum((Decimal(b.precio) for b in pagadas), Decimal(0))
        pago_ids = {b.pago_id for b in pagadas if b.pago_id}

        if afectadas:
            Boleta.objects.filter(id__in=[b.id for b in afectadas]).update(
                estado=Boleta.Estado.CANCELADA,
                motivo_cancelacion=Boleta.MotivoCancelacion.EVENTO_CANCELADO,
                expira_en=None,
            )
            for localidad_id, n in Counter(b.localidad_id for b in afectadas).items():
                self._localidad_repo.ajustar_vendidas(localidad_id, -n)

        reembolsos = 0
        for pago in Pago.objects.filter(id__in=pago_ids):
            self._pasarela.reembolsar(
                pago.referencia,
                sum((Decimal(b.precio) for b in pagadas if b.pago_id == pago.id), Decimal(0)),
            )
            reembolsos += 1
        Pago.objects.filter(id__in=pago_ids).exclude(
            boletas__estado__in=[Boleta.Estado.PAGADA, Boleta.Estado.USADA]
        ).update(estado=Pago.Estado.REEMBOLSADO)

        evento.estado = Evento.Estado.CANCELADO
        self._evento_repo.guardar(evento)

        if afectadas:
            transaction.on_commit(lambda: _encolar_notificacion_cancelacion(evento.id, datos.motivo))
        return ResultadoCancelacionEvento(
            evento=evento, boletas_canceladas=len(afectadas),
            reembolsos=reembolsos, monto_reembolsado=monto_reembolsado,
        )


def _encolar_notificacion_cancelacion(evento_id: int, motivo: str) -> None:
    from apps.reportes.tasks import notificar_cancelacion_evento

    try:
        # retry=False: si el broker está caído falla rápido en vez de bloquear la petición.
        notificar_cancelacion_evento.apply_async(args=(evento_id, motivo), retry=False)
    except Exception:  # noqa: BLE001 - broker caído no debe tumbar la petición
        logger.exception("No se pudo encolar la notificación de cancelación del evento %s", evento_id)
