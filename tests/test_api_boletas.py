"""
Tests de integración: usan el cliente de pruebas de DRF contra la BD de
prueba (sqlite en memoria) para validar el flujo completo
Vista -> Service -> Builder -> ORM, incluyendo códigos HTTP.
"""

from django.contrib.auth import get_user_model
from django.urls import reverse
from django.utils import timezone
from rest_framework.test import APITestCase

from apps.eventos.models import CategoriaEvento, Evento, Localidad, Organizador

Usuario = get_user_model()


class ReservaBoletaAPITests(APITestCase):
    def setUp(self):
        self.usuario = Usuario.objects.create_user(username="camilo", password="clave12345")
        organizador_user = Usuario.objects.create_user(username="promotora", password="clave12345")
        organizador = Organizador.objects.create(
            usuario=organizador_user, nombre_empresarial="Promotora EAFIT"
        )
        categoria = CategoriaEvento.objects.create(nombre="Concierto")
        self.evento = Evento.objects.create(
            organizador=organizador,
            categoria=categoria,
            titulo="Rock al Parque",
            lugar="Medellín",
            fecha_evento=timezone.now() + timezone.timedelta(days=30),
            estado=Evento.Estado.PUBLICADO,
        )
        self.localidad = Localidad.objects.create(
            evento=self.evento, nombre="VIP", precio=150000, cupo=2, vendidas=0
        )

    def test_reservar_boleta_devuelve_201(self):
        self.client.force_authenticate(self.usuario)
        respuesta = self.client.post(
            reverse("api:boleta-reservar"),
            {"evento_id": self.evento.id, "localidad_id": self.localidad.id},
        )
        self.assertEqual(respuesta.status_code, 201)
        self.assertEqual(respuesta.data["estado"], "RESERVADA")
        self.localidad.refresh_from_db()
        self.assertEqual(self.localidad.vendidas, 1)

    def test_reservar_sin_cupo_devuelve_409(self):
        self.localidad.vendidas = 2  # cupo lleno
        self.localidad.save()

        self.client.force_authenticate(self.usuario)
        respuesta = self.client.post(
            reverse("api:boleta-reservar"),
            {"evento_id": self.evento.id, "localidad_id": self.localidad.id},
        )
        self.assertEqual(respuesta.status_code, 409)

    def test_reservar_localidad_inexistente_devuelve_404(self):
        self.client.force_authenticate(self.usuario)
        respuesta = self.client.post(
            reverse("api:boleta-reservar"),
            {"evento_id": self.evento.id, "localidad_id": 9999},
        )
        self.assertEqual(respuesta.status_code, 404)

    def test_reservar_sin_autenticar_devuelve_401_o_403(self):
        respuesta = self.client.post(
            reverse("api:boleta-reservar"),
            {"evento_id": self.evento.id, "localidad_id": self.localidad.id},
        )
        self.assertIn(respuesta.status_code, (401, 403))

    def test_cancelar_boleta_libera_cupo(self):
        self.client.force_authenticate(self.usuario)
        reserva = self.client.post(
            reverse("api:boleta-reservar"),
            {"evento_id": self.evento.id, "localidad_id": self.localidad.id},
        )
        boleta_id = reserva.data["id"]

        respuesta = self.client.post(reverse("api:boleta-cancelar", args=[boleta_id]))
        self.assertEqual(respuesta.status_code, 200)
        self.assertEqual(respuesta.data["estado"], "CANCELADA")

        self.localidad.refresh_from_db()
        self.assertEqual(self.localidad.vendidas, 0)
