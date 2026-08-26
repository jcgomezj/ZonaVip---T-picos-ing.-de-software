"""
Tests de dominio puro: no requieren base de datos porque `BoletaBuilder`
no depende de Django ORM, solo del contrato mínimo de `localidad`
(`.id`, `.nombre`, `.precio`, `.hay_cupo()`). Se pueden correr con
`python manage.py test tests` o directamente con `pytest`.
"""

from django.test import SimpleTestCase

from domain.builders.boleta_builder import BoletaBuilder, BoletaInvalidaError, SinCupoError


class LocalidadFake:
    def __init__(self, nombre="VIP", precio=100000, cupo=10, vendidas=0):
        self.id = 1
        self.nombre = nombre
        self.precio = precio
        self.cupo = cupo
        self.vendidas = vendidas

    def hay_cupo(self) -> bool:
        return self.vendidas < self.cupo


class BoletaBuilderTests(SimpleTestCase):
    def test_construye_boleta_valida(self):
        localidad = LocalidadFake(cupo=10, vendidas=2)

        boleta = (
            BoletaBuilder()
            .para_usuario(42)
            .para_evento(7)
            .en_localidad(localidad)
            .generar_codigo_qr()
            .marcar_reservada_ahora()
            .build()
        )

        self.assertEqual(boleta.usuario_id, 42)
        self.assertEqual(boleta.evento_id, 7)
        self.assertEqual(boleta.estado, "RESERVADA")
        self.assertIsNotNone(boleta.codigo_qr)
        self.assertEqual(boleta.precio, 100000)

    def test_rechaza_localidad_sin_cupo(self):
        localidad = LocalidadFake(cupo=5, vendidas=5)

        with self.assertRaises(SinCupoError):
            BoletaBuilder().para_usuario(42).en_localidad(localidad)

    def test_rechaza_usuario_invalido(self):
        with self.assertRaises(BoletaInvalidaError):
            BoletaBuilder().para_usuario(None)

    def test_build_sin_localidad_falla(self):
        with self.assertRaises(BoletaInvalidaError):
            BoletaBuilder().para_usuario(1).para_evento(1).build()

    def test_build_genera_qr_si_se_olvido_pedirlo(self):
        localidad = LocalidadFake(cupo=10, vendidas=0)
        boleta = (
            BoletaBuilder()
            .para_usuario(1)
            .para_evento(1)
            .en_localidad(localidad)
            .build()
        )
        self.assertIsNotNone(boleta.codigo_qr)
        self.assertIsNotNone(boleta.reservada_en)
