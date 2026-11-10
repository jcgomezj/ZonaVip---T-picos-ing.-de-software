"""
Capa de presentación (Django Rest Framework).

Cada vista es una `APIView` delgada: parsea/valida forma con un
Serializer, arma un DTO, delega TODO el trabajo a un Service, y traduce
la excepción de dominio (si la hay) a un código HTTP. Ninguna vista supera
las ~15 líneas de lógica propia, y ninguna toca el ORM directamente.

Mapeo de excepciones de dominio -> HTTP (ver domain/exceptions.py):
    ValidacionNegocioError   -> 400
    PagoRechazadoError       -> 402
    PermisoDenegadoError     -> 403
    RecursoNoEncontradoError -> 404
    ConflictoEstadoError     -> 409

Todo error tiene la forma {"error": <mensaje>, "codigo": <código estable>, ...extra}.
"""

from rest_framework import status
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.throttling import ScopedRateThrottle
from rest_framework.views import APIView

from apps.eventos.models import Evento, Organizador
from application.queries import resumen_organizador
from application.services import (
    CancelarBoletaService,
    CancelarEventoDTO,
    CancelarEventoService,
    CompraBoletasDTO,
    CompraBoletasService,
    CrearEventoDTO,
    CrearEventoService,
    PagarReservaDTO,
    PagarReservaService,
    PublicarEventoService,
    ReservaBoletaDTO,
    ReservaBoletaService,
    ValidarBoletaDTO,
    ValidarBoletaService,
)
from domain.exceptions import (
    ConflictoEstadoError,
    DomainError,
    PagoRechazadoError,
    PermisoDenegadoError,
    RecursoNoEncontradoError,
    ValidacionNegocioError,
)

from .serializers import (
    BoletaSerializer,
    CancelarEventoInputSerializer,
    CompraBoletasInputSerializer,
    CrearEventoInputSerializer,
    EventoSerializer,
    PagarReservaInputSerializer,
    ReservaBoletaInputSerializer,
    ValidarBoletaInputSerializer,
)


def _respuesta_error_dominio(error: Exception) -> Response:
    """Único punto que traduce una excepción de dominio a HTTP.
    Reutilizado por todas las vistas para mantener un contrato de error
    uniforme en toda la API (clave para estandarizar detrás de un Gateway)."""
    if isinstance(error, RecursoNoEncontradoError):
        codigo = status.HTTP_404_NOT_FOUND
    elif isinstance(error, PermisoDenegadoError):
        codigo = status.HTTP_403_FORBIDDEN
    elif isinstance(error, PagoRechazadoError):
        codigo = status.HTTP_402_PAYMENT_REQUIRED
    elif isinstance(error, ConflictoEstadoError):
        codigo = status.HTTP_409_CONFLICT
    elif isinstance(error, ValidacionNegocioError):
        codigo = status.HTTP_400_BAD_REQUEST
    else:
        raise error
    cuerpo = {"error": str(error), "codigo": error.codigo}
    cuerpo.update(getattr(error, "extra", {}))
    return Response(cuerpo, status=codigo)


class EventoListCreateView(APIView):
    """
    GET  /api/eventos/  -> lista pública de eventos PUBLICADOS
    POST /api/eventos/  -> un organizador crea un evento (queda en BORRADOR)
    """

    def get_permissions(self):
        if self.request.method == "POST":
            return [IsAuthenticated()]
        return []

    def get(self, request):
        eventos = (
            Evento.objects.filter(estado=Evento.Estado.PUBLICADO)
            .select_related("organizador", "categoria")
            .prefetch_related("localidades")
        )
        categoria_id = request.query_params.get("categoria")
        if categoria_id:
            eventos = eventos.filter(categoria_id=categoria_id)

        q = request.query_params.get("q")
        if q:
            eventos = eventos.filter(titulo__icontains=q.strip())

        return Response(EventoSerializer(eventos, many=True).data)

    def post(self, request):
        entrada = CrearEventoInputSerializer(data=request.data)
        entrada.is_valid(raise_exception=True)

        try:
            organizador = Organizador.objects.get(usuario=request.user)
        except Organizador.DoesNotExist:
            return _respuesta_error_dominio(RecursoNoEncontradoError(
                "El usuario autenticado no tiene un perfil de organizador.",
                codigo="sin_perfil_organizador",
            ))

        dto = CrearEventoDTO(organizador_id=organizador.id, **entrada.validated_data)

        try:
            evento = CrearEventoService().ejecutar(dto)
        except DomainError as error:
            return _respuesta_error_dominio(error)

        evento_optimizado = (
            Evento.objects.select_related("organizador", "categoria")
            .prefetch_related("localidades")
            .get(id=evento.id)
        )
        return Response(EventoSerializer(evento_optimizado).data, status=status.HTTP_201_CREATED)


class EventoPublicarView(APIView):
    """POST /api/eventos/<id>/publicar/ -> BORRADOR -> PUBLICADO"""

    permission_classes = [IsAuthenticated]

    def post(self, request, evento_id):
        try:
            organizador = Organizador.objects.get(usuario=request.user)
        except Organizador.DoesNotExist:
            return _respuesta_error_dominio(RecursoNoEncontradoError(
                "El usuario autenticado no tiene un perfil de organizador.",
                codigo="sin_perfil_organizador",
            ))

        try:
            evento = PublicarEventoService().ejecutar(evento_id, organizador.id)
        except DomainError as error:
            return _respuesta_error_dominio(error)

        evento_optimizado = (
            Evento.objects.select_related("organizador", "categoria")
            .prefetch_related("localidades")
            .get(id=evento.id)
        )
        return Response(EventoSerializer(evento_optimizado).data, status=status.HTTP_200_OK)


class ReservarBoletaView(APIView):
    """POST /api/boletas/reservar/ -> reserva una boleta para el usuario autenticado."""

    permission_classes = [IsAuthenticated]
    service_class = ReservaBoletaService

    def post(self, request):
        entrada = ReservaBoletaInputSerializer(data=request.data)
        entrada.is_valid(raise_exception=True)

        dto = ReservaBoletaDTO(usuario_id=request.user.id, **entrada.validated_data)

        try:
            boleta = self.service_class().ejecutar(dto)
        except DomainError as error:
            return _respuesta_error_dominio(error)

        return Response(BoletaSerializer(boleta).data, status=status.HTTP_201_CREATED)


def _clave_idempotencia(request, validada: dict):
    """`Idempotency-Key` (cabecera estándar) o `idempotency_key` en el cuerpo."""
    return request.headers.get("Idempotency-Key") or validada.get("idempotency_key") or None


def _respuesta_compra(request, resultado) -> Response:
    boletas, pago = resultado.boletas, resultado.pago
    respuesta = Response(
        {
            "cantidad": len(boletas),
            "total": str(sum(b.precio for b in boletas)),
            "correo": request.user.email,
            "repetida": resultado.repetida,
            "pago": {"referencia": pago.referencia, "monto": str(pago.monto),
                     "metodo": pago.metodo, "estado": pago.estado},
            "boletas": [
                {**BoletaSerializer(b).data, "qr_url": f"/boletas/{b.codigo_qr}/qr.png"}
                for b in boletas
            ],
        },
        status=status.HTTP_200_OK if resultado.repetida else status.HTTP_201_CREATED,
    )
    if resultado.repetida:
        respuesta["Idempotent-Replayed"] = "true"
    return respuesta


class ComprarBoletasView(APIView):
    """POST /api/boletas/comprar/ -> cobra y emite N boletas PAGADAS.

    Cuerpo: evento_id, localidad_id, cantidad, [metodo_pago, token_pago].
    Cabecera recomendada `Idempotency-Key`: un reintento con la misma clave NO
    vuelve a cobrar (200 + `Idempotent-Replayed: true`). Pago rechazado -> 402.
    """

    permission_classes = [IsAuthenticated]
    throttle_classes = [ScopedRateThrottle]
    throttle_scope = "compra"

    def post(self, request):
        entrada = CompraBoletasInputSerializer(data=request.data)
        entrada.is_valid(raise_exception=True)
        datos = dict(entrada.validated_data)
        clave = _clave_idempotencia(request, datos)
        datos.pop("idempotency_key", None)
        dto = CompraBoletasDTO(usuario_id=request.user.id, idempotency_key=clave, **datos)
        try:
            resultado = CompraBoletasService().ejecutar(dto)
        except DomainError as error:
            return _respuesta_error_dominio(error)
        return _respuesta_compra(request, resultado)


class PagarReservaView(APIView):
    """POST /api/boletas/<id>/pagar/ -> paga una reserva vigente."""

    permission_classes = [IsAuthenticated]
    throttle_classes = [ScopedRateThrottle]
    throttle_scope = "compra"

    def post(self, request, boleta_id):
        entrada = PagarReservaInputSerializer(data=request.data)
        entrada.is_valid(raise_exception=True)
        datos = dict(entrada.validated_data)
        clave = _clave_idempotencia(request, datos)
        datos.pop("idempotency_key", None)
        dto = PagarReservaDTO(boleta_id=boleta_id, usuario_id=request.user.id,
                              idempotency_key=clave, **datos)
        try:
            resultado = PagarReservaService().ejecutar(dto)
        except DomainError as error:
            return _respuesta_error_dominio(error)
        return _respuesta_compra(request, resultado)


class ValidarBoletaView(APIView):
    """POST /api/boletas/validar/ -> check-in en el ingreso.

    Cuerpo: {"codigo": "<payload del QR o código>", "evento_id": <opcional>}.
    Solo staff u organizador del evento. 200 = puede ingresar (queda USADA);
    409 ya_usada/cancelada/sin_pago...; 404 inexistente; 400 QR inválido/vencido;
    403 sin permiso."""

    permission_classes = [IsAuthenticated]
    throttle_classes = [ScopedRateThrottle]
    throttle_scope = "checkin"

    def post(self, request):
        entrada = ValidarBoletaInputSerializer(data=request.data)
        entrada.is_valid(raise_exception=True)
        dto = ValidarBoletaDTO(
            codigo=entrada.validated_data["codigo"], evento_id=entrada.validated_data["evento_id"],
            validador_id=request.user.id, es_staff=request.user.is_staff,
        )
        try:
            resultado = ValidarBoletaService().ejecutar(dto)
        except DomainError as error:
            return _respuesta_error_dominio(error)
        b = resultado.boleta
        return Response({
            "valido": True, "tipo_qr": resultado.tipo_qr,
            "boleta": {
                "id": b.id, "codigo_qr": b.codigo_qr, "estado": b.estado, "usada_en": b.usada_en,
                "evento": {"id": b.evento_id, "titulo": b.evento.titulo},
                "localidad": {"id": b.localidad_id, "nombre": b.localidad.nombre, "tipo": b.localidad.tipo},
                "asistente": b.usuario.get_full_name() or b.usuario.get_username(),
            },
        })


class EventoCancelarView(APIView):
    """POST /api/eventos/<id>/cancelar/ -> cancela evento y boletas, reembolsa y
    encola (Celery) el aviso por correo. Solo organizador del evento o admin."""

    permission_classes = [IsAuthenticated]

    def post(self, request, evento_id):
        entrada = CancelarEventoInputSerializer(data=request.data)
        entrada.is_valid(raise_exception=True)
        dto = CancelarEventoDTO(evento_id=evento_id, usuario_id=request.user.id,
                                es_staff=request.user.is_staff, motivo=entrada.validated_data["motivo"])
        try:
            r = CancelarEventoService().ejecutar(dto)
        except DomainError as error:
            return _respuesta_error_dominio(error)
        return Response({
            "evento_id": r.evento.id, "estado": r.evento.estado,
            "boletas_canceladas": r.boletas_canceladas, "reembolsos": r.reembolsos,
            "monto_reembolsado": str(r.monto_reembolsado),
            "notificacion": "encolada" if r.boletas_canceladas else "no_aplica",
        })


class OrganizadorResumenView(APIView):
    """GET /api/organizador/resumen/ -> ventas por localidad y ocupación.
    Organizador: solo sus eventos. Admin: todos (o ?organizador_id=)."""

    permission_classes = [IsAuthenticated]

    def get(self, request):
        organizador = Organizador.objects.filter(usuario=request.user).first()
        if organizador is not None:
            organizador_id = organizador.id
        elif request.user.is_staff:
            pedido = request.query_params.get("organizador_id", "")
            organizador_id = int(pedido) if pedido.isdigit() else None
        else:
            return _respuesta_error_dominio(
                PermisoDenegadoError("El usuario no tiene un perfil de organizador."))
        return Response(resumen_organizador(organizador_id))


class CancelarBoletaView(APIView):
    """POST /api/boletas/<id>/cancelar/"""

    permission_classes = [IsAuthenticated]

    def post(self, request, boleta_id):
        try:
            boleta = CancelarBoletaService().ejecutar(boleta_id, request.user.id)
        except DomainError as error:
            return _respuesta_error_dominio(error)

        return Response(BoletaSerializer(boleta).data, status=status.HTTP_200_OK)


class MisBoletasView(APIView):
    """GET /api/boletas/mias/ -> boletas del usuario autenticado."""

    permission_classes = [IsAuthenticated]

    def get(self, request):
        boletas = request.user.boletas.select_related(
            "evento", "evento__organizador", "evento__categoria", "localidad"
        )
        return Response(BoletaSerializer(boletas, many=True).data)
