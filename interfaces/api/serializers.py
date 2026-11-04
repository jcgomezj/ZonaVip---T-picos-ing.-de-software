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
    imagen_url = serializers.CharField(read_only=True)
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
            "tipo_recinto",
            "imagen_url",
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


METODOS_PAGO = ("TARJETA", "PSE", "NEQUI")


class DatosPagoMixin(serializers.Serializer):
    """Campos de pago compartidos. `token_pago` es opaco (como el de un SDK real
    tras tokenizar la tarjeta); nunca se reciben números de tarjeta."""

    metodo_pago = serializers.ChoiceField(choices=METODOS_PAGO, default="TARJETA")
    token_pago = serializers.CharField(max_length=64, default="tok_ok")
    idempotency_key = serializers.CharField(max_length=64, required=False, allow_blank=True, default="")


class CompraBoletasInputSerializer(DatosPagoMixin):
    """Serializer de ENTRADA para POST /api/boletas/comprar/."""

    evento_id = serializers.IntegerField()
    localidad_id = serializers.IntegerField()
    cantidad = serializers.IntegerField(min_value=1, max_value=8)


class PagarReservaInputSerializer(DatosPagoMixin):
    """ENTRADA para POST /api/boletas/<id>/pagar/."""


class ValidarBoletaInputSerializer(serializers.Serializer):
    """ENTRADA para POST /api/boletas/validar/ (check-in)."""

    codigo = serializers.CharField(max_length=200)
    evento_id = serializers.IntegerField(required=False, allow_null=True, default=None)


class CancelarEventoInputSerializer(serializers.Serializer):
    motivo = serializers.CharField(max_length=300, required=False, allow_blank=True, default="")


class ReporteVentasInputSerializer(serializers.Serializer):
    evento_id = serializers.IntegerField(required=False, allow_null=True, default=None)


class NotificacionMasivaInputSerializer(serializers.Serializer):
    mensaje = serializers.CharField(max_length=500)
    destinatarios = serializers.IntegerField(min_value=1, max_value=10000, default=100)


class BoletaSerializer(serializers.ModelSerializer):
    pago_referencia = serializers.CharField(source="pago.referencia", read_only=True, default=None)

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
            "expira_en",
            "usada_en",
            "pago_referencia",
            "creado_en",
        ]
