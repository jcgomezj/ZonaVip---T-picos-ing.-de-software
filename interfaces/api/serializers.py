"""
Serializers: SOLO validan forma y tipo de los datos (entrada) o dan forma
a la respuesta (salida). Ninguna regla de negocio vive aquí -> eso es
responsabilidad exclusiva de `application/services.py`.
"""

from rest_framework import serializers

from apps.boletas.models import Boleta
from apps.eventos.models import CategoriaEvento, Evento, Localidad


class CategoriaEventoSerializer(serializers.ModelSerializer):
    class Meta:
        model = CategoriaEvento
        fields = ["id", "nombre", "descripcion"]


class LocalidadSerializer(serializers.ModelSerializer):
    cupo_disponible = serializers.SerializerMethodField()

    class Meta:
        model = Localidad
        fields = ["id", "nombre", "tipo", "precio", "cupo", "vendidas", "cupo_disponible"]

    def get_cupo_disponible(self, obj) -> int:
        return obj.cupo - obj.vendidas


class EventoSerializer(serializers.ModelSerializer):
    """Serializer de SALIDA: evento con sus localidades anidadas."""

    localidades = LocalidadSerializer(many=True, read_only=True)
    organizador_nombre = serializers.CharField(
        source="organizador.nombre_empresarial", read_only=True
    )

    class Meta:
        model = Evento
        fields = [
            "id",
            "titulo",
            "descripcion",
            "lugar",
            "fecha_evento",
            "estado",
            "categoria",
            "organizador_nombre",
            "localidades",
            "creado_en",
        ]
        read_only_fields = ["estado", "creado_en"]


class CrearEventoInputSerializer(serializers.Serializer):
    """Serializer de ENTRADA para POST /api/eventos/.
    Solo valida tipos/formato; el Service valida reglas de negocio."""

    categoria_id = serializers.IntegerField()
    titulo = serializers.CharField(max_length=150)
    descripcion = serializers.CharField(required=False, allow_blank=True, default="")
    lugar = serializers.CharField(max_length=200)
    fecha_evento = serializers.DateTimeField()


class ReservaBoletaInputSerializer(serializers.Serializer):
    """Serializer de ENTRADA para POST /api/boletas/reservar/."""

    evento_id = serializers.IntegerField()
    localidad_id = serializers.IntegerField()


class BoletaSerializer(serializers.ModelSerializer):
    class Meta:
        model = Boleta
        fields = [
            "id",
            "evento",
            "localidad",
            "codigo_qr",
            "precio",
            "estado",
            "reservada_en",
            "creado_en",
        ]
