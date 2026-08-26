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

        return Response(EventoSerializer(evento).data, status=status.HTTP_201_CREATED)


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

        return Response(EventoSerializer(evento).data, status=status.HTTP_200_OK)


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
        boletas = request.user.boletas.select_related("evento", "localidad")
        return Response(BoletaSerializer(boletas, many=True).data)
