"""
Ejecutar:
    python tests_demo.py
    ENV_TYPE=REAL python tests_demo.py
"""

import os
import sys

sys.path.insert(0, os.path.dirname(__file__))

from domain.builders.boleta_builder import BoletaBuilder, BoletaInvalidaError
from infra.factories.notificador_factory import NotificadorFactory


class LocalidadFake:
    def __init__(self, nombre, precio, cupo, vendidas):
        self.id = 1
        self.nombre = nombre
        self.precio = precio
        self.cupo = cupo
        self.vendidas = vendidas

    def hay_cupo(self):
        return self.vendidas < self.cupo


def demo_builder():
    print("== Demo Builder ==")
    localidad_con_cupo = LocalidadFake("Platea", 120000, cupo=100, vendidas=10)

    boleta = (
        BoletaBuilder()
        .para_usuario(usuario_id=42)
        .para_evento(evento_id=7)
        .en_localidad(localidad_con_cupo)
        .generar_codigo_qr()
        .marcar_reservada_ahora()
        .build()
    )
    print("Boleta construida correctamente:", boleta)

    localidad_sin_cupo = LocalidadFake("VIP", 300000, cupo=5, vendidas=5)
    try:
        (
            BoletaBuilder()
            .para_usuario(usuario_id=42)
            .en_localidad(localidad_sin_cupo)
            .build()
        )
    except BoletaInvalidaError as e:
        print("Rechazado correctamente ->", e)


def demo_factory():
    print("\n== Demo Factory ==")
    print("ENV_TYPE actual:", os.environ.get("ENV_TYPE", "MOCK (default)"))
    notificador = NotificadorFactory.crear()
    print("Implementación instanciada:", notificador.__class__.__name__)


if __name__ == "__main__":
    demo_builder()
    demo_factory()
