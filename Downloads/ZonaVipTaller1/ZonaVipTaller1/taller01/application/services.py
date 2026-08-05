

from dataclasses import dataclass

from domain.builders.boleta_builder import BoletaBuilder, BoletaInvalidaError
from infra.factories.notificador_factory import NotificadorFactory


@dataclass
class ReservaBoletaDTO:
    usuario_id: int
    localidad_id: int
    evento_id: int


class LocalidadRepository:


    def obtener_por_id(self, localidad_id: int):
        from apps.eventos.models import Localidad  
        return Localidad.objects.select_for_update().get(id=localidad_id)


class BoletaRepository:
    def guardar(self, boleta_data):
        from apps.eventos.models import Boleta
        return Boleta.objects.create(**boleta_data.__dict__)


class ReservaBoletaService:


    def __init__(
        self,
        localidad_repo: LocalidadRepository = None,
        boleta_repo: BoletaRepository = None,
    ):
        
        self._localidad_repo = localidad_repo or LocalidadRepository()
        self._boleta_repo = boleta_repo or BoletaRepository()
        self._notificador = NotificadorFactory.crear()

    def ejecutar(self, datos: ReservaBoletaDTO):
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
