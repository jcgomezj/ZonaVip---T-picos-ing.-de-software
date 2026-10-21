"""
Capa de presentación (Django Rest Framework).

Cada vista es una `APIView` delgada: parsea/valida forma con un
Serializer, arma un DTO, delega TODO el trabajo a un Service, y traduce
la excepción de dominio (si la hay) a un código HTTP. Ninguna vista supera
las ~15 líneas de lógica propia, y ninguna toca el ORM directamente.

Mapeo de excepciones de dominio -> HTTP (ver domain/exceptions.py):
    ValidacionNegocioError  -> 400
    RecursoNoEncontradoError -> 404
    ConflictoEstadoError     -> 409
"""

from rest_framework import status
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.eventos.models import Evento, Organizador
from application.services import (
    CancelarBoletaService,
    CompraBoletasDTO,
    CompraBoletasService,
    CrearEventoDTO,
    CrearEventoService,
    PublicarEventoService,
    ReservaBoletaDTO,
    ReservaBoletaService,
)
from domain.exceptions import (
    ConflictoEstadoError,
    RecursoNoEncontradoError,
    ValidacionNegocioError,
)

from .serializers import (
    BoletaSerializer,
    CompraBoletasInputSerializer,
    CrearEventoInputSerializer,
    EventoSerializer,
    ReservaBoletaInputSerializer,
)


def _respuesta_error_dominio(error: Exception) -> Response:
    """Único punto que traduce una excepción de dominio a HTTP.
    Reutilizado por todas las vistas para mantener un contrato de error
    uniforme en toda la API (clave para estandarizar detrás de un Gateway)."""
    if isinstance(error, RecursoNoEncontradoError):
        codigo = status.HTTP_404_NOT_FOUND
    elif isinstance(error, ConflictoEstadoError):
        codigo = status.HTTP_409_CONFLICT
    elif isinstance(error, ValidacionNegocioError):
        codigo = status.HTTP_400_BAD_REQUEST
    else:
        raise error
    return Response({"error": str(error)}, status=codigo)


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
            return Response(
                {"error": "El usuario autenticado no tiene un perfil de organizador."},
                status=status.HTTP_404_NOT_FOUND,
            )

        dto = CrearEventoDTO(organizador_id=organizador.id, **entrada.validated_data)

        try:
            evento = CrearEventoService().ejecutar(dto)
        except (ValidacionNegocioError, RecursoNoEncontradoError) as error:
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
            return Response(
                {"error": "El usuario autenticado no tiene un perfil de organizador."},
                status=status.HTTP_404_NOT_FOUND,
            )

        try:
            evento = PublicarEventoService().ejecutar(evento_id, organizador.id)
        except (ValidacionNegocioError, RecursoNoEncontradoError, ConflictoEstadoError) as error:
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
        except (ValidacionNegocioError, RecursoNoEncontradoError, ConflictoEstadoError) as error:
            return _respuesta_error_dominio(error)

        return Response(BoletaSerializer(boleta).data, status=status.HTTP_201_CREATED)


class ComprarBoletasView(APIView):
    """POST /api/boletas/comprar/ -> compra N boletas (solo usuarios con sesión).

    Responde con las boletas emitidas y la URL del QR de cada una; el correo de
    confirmación lo dispara el Service al confirmar la transacción.
    """

    permission_classes = [IsAuthenticated]

    def post(self, request):
        entrada = CompraBoletasInputSerializer(data=request.data)
        entrada.is_valid(raise_exception=True)
        dto = CompraBoletasDTO(usuario_id=request.user.id, **entrada.validated_data)

        try:
            boletas = CompraBoletasService().ejecutar(dto)
        except (ValidacionNegocioError, RecursoNoEncontradoError, ConflictoEstadoError) as error:
            return _respuesta_error_dominio(error)

        total = sum(b.precio for b in boletas)
        return Response(
            {
                "cantidad": len(boletas),
                "total": str(total),
                "correo": request.user.email,
                "boletas": [
                    {**BoletaSerializer(b).data, "qr_url": f"/boletas/{b.codigo_qr}/qr.png"}
                    for b in boletas
                ],
            },
            status=status.HTTP_201_CREATED,
        )


class CancelarBoletaView(APIView):
    """POST /api/boletas/<id>/cancelar/"""

    permission_classes = [IsAuthenticated]

    def post(self, request, boleta_id):
        try:
            boleta = CancelarBoletaService().ejecutar(boleta_id, request.user.id)
        except (RecursoNoEncontradoError, ConflictoEstadoError) as error:
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
