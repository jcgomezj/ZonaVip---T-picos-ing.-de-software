"""Tests de la entrega final: exportación de asistentes a CSV, API resiliente
cuando el broker (Redis) está caído, errores uniformes y páginas de error."""

import csv
import io
from datetime import timedelta
from unittest import mock

from django.contrib.auth import get_user_model
from django.test import TestCase, override_settings
from django.urls import reverse
from django.utils import timezone
from rest_framework.test import APITestCase

from apps.boletas.models import Boleta
from apps.eventos.models import CategoriaEvento, Evento, Localidad, Organizador
from interfaces.web.views import _celda_csv

Usuario = get_user_model()


def _boleta(usuario, evento, localidad, estado, codigo, **extra):
    return Boleta.objects.create(
        usuario=usuario, evento=evento, localidad=localidad, codigo_qr=codigo,
        precio=localidad.precio, estado=estado, reservada_en=timezone.now(), **extra,
    )


class _Escenario(TestCase):
    def setUp(self):
        self.org_user = Usuario.objects.create_user(username="org", password="x12345678")
        org = Organizador.objects.create(usuario=self.org_user, nombre_empresarial="Org SAS")
        cat = CategoriaEvento.objects.create(nombre="Concierto")
        self.ev = Evento.objects.create(
            organizador=org, categoria=cat, titulo="Show", lugar="Estadio",
            fecha_evento=timezone.now() + timedelta(days=5), estado=Evento.Estado.PUBLICADO,
        )
        self.loc = Localidad.objects.create(evento=self.ev, nombre="Norte", precio=100000, cupo=10)

        otro_org = Usuario.objects.create_user(username="org2", password="x12345678")
        self.org2 = Organizador.objects.create(usuario=otro_org, nombre_empresarial="Otra")
        self.org2_user = otro_org
        self.staff = Usuario.objects.create_user(username="staff", password="x12345678", is_staff=True)

        self.ana = Usuario.objects.create_user(
            username="ana", email="ana@x.co", password="x12345678", first_name="Ana", last_name="Gómez",
        )
        self.malo = Usuario.objects.create_user(username="=HYPERLINK(1)", email="m@x.co", password="x12345678")

        _boleta(self.ana, self.ev, self.loc, Boleta.Estado.PAGADA, "c-pagada")
        _boleta(self.malo, self.ev, self.loc, Boleta.Estado.USADA, "c-usada",
                usada_en=timezone.now(), validada_por=self.staff)
        _boleta(self.ana, self.ev, self.loc, Boleta.Estado.CANCELADA, "c-cancelada")
        _boleta(self.ana, self.ev, self.loc, Boleta.Estado.RESERVADA, "c-reservada")
        self.url = reverse("web:organizador-asistentes-csv", args=[self.ev.id])

    def filas(self, respuesta):
        texto = respuesta.content.decode("utf-8")
        self.assertTrue(texto.startswith("﻿"), "El CSV debe llevar BOM para Excel")
        return list(csv.reader(io.StringIO(texto.lstrip("﻿"))))


class AsistentesCsvTests(_Escenario):
    def test_organizador_descarga_solo_boletas_cobradas(self):
        self.client.force_login(self.org_user)
        r = self.client.get(self.url)
        self.assertEqual(r.status_code, 200)
        self.assertIn("text/csv", r["Content-Type"])
        self.assertIn(f'filename="asistentes-evento-{self.ev.id}-', r["Content-Disposition"])
        filas = self.filas(r)
        self.assertEqual(filas[0][0], "Código")
        codigos = sorted(f[0] for f in filas[1:])
        self.assertEqual(codigos, ["c-pagada", "c-usada"])  # sin canceladas ni reservas

        ana = next(f for f in filas[1:] if f[0] == "c-pagada")
        self.assertEqual(ana[1:6], ["Ana Gómez", "ana", "ana@x.co", "Norte", "100000"])
        self.assertEqual(ana[8], "")  # aún no ingresa

        usada = next(f for f in filas[1:] if f[0] == "c-usada")
        self.assertNotEqual(usada[8], "")
        self.assertEqual(usada[9], "staff")

    def test_neutraliza_inyeccion_de_formulas(self):
        self.client.force_login(self.org_user)
        usada = next(f for f in self.filas(self.client.get(self.url))[1:] if f[0] == "c-usada")
        self.assertEqual(usada[2], "'=HYPERLINK(1)")
        self.assertEqual(_celda_csv("+57 300"), "'+57 300")
        self.assertEqual(_celda_csv("normal"), "normal")
        self.assertEqual(_celda_csv(None), "")

    def test_otro_organizador_recibe_404(self):
        self.client.force_login(self.org2_user)
        self.assertEqual(self.client.get(self.url).status_code, 404)

    def test_comprador_sin_rol_recibe_404_y_anonimo_va_al_login(self):
        self.client.force_login(self.ana)
        self.assertEqual(self.client.get(self.url).status_code, 404)
        self.client.logout()
        r = self.client.get(self.url)
        self.assertEqual(r.status_code, 302)
        self.assertIn(reverse("web:login"), r["Location"])

    def test_admin_exporta_cualquier_evento(self):
        self.client.force_login(self.staff)
        self.assertEqual(len(self.filas(self.client.get(self.url))), 3)

    def test_evento_inexistente_404(self):
        self.client.force_login(self.staff)
        r = self.client.get(reverse("web:organizador-asistentes-csv", args=[99999]))
        self.assertEqual(r.status_code, 404)

    def test_panel_muestra_boton_de_descarga(self):
        self.client.force_login(self.org_user)
        self.assertContains(self.client.get(reverse("web:organizador")), self.url)


class BrokerCaidoTests(APITestCase):
    """Si Redis no responde, la API devuelve 503 en vez de colgarse."""

    def setUp(self):
        self.admin = Usuario.objects.create_user(username="adm", password="x12345678", is_staff=True)
        self.client.force_authenticate(self.admin)

    def test_reporte_y_notificacion_devuelven_503(self):
        casos = [
            ("apps.reportes.tasks.generar_reporte_ventas.apply_async", reverse("api:reporte-ventas"), {}),
            ("apps.reportes.tasks.enviar_notificacion_masiva.apply_async", reverse("api:notificacion-masiva"),
             {"mensaje": "Hola", "destinatarios": 3}),
        ]
        for objetivo, url, cuerpo in casos:
            with self.subTest(url=url), mock.patch(objetivo, side_effect=ConnectionError("redis caído")):
                r = self.client.post(url, cuerpo, format="json")
                self.assertEqual(r.status_code, 503)
                self.assertEqual(r.data["codigo"], "broker_no_disponible")

    def test_reporte_encolado_devuelve_202(self):
        r = self.client.post(reverse("api:reporte-ventas"), {}, format="json")
        self.assertEqual(r.status_code, 202)
        self.assertEqual(r.data["estado"], "encolado")


class ErroresUniformesTests(APITestCase):
    def test_crear_evento_sin_perfil_organizador_trae_codigo(self):
        u = Usuario.objects.create_user(username="sinorg", password="x12345678")
        self.client.force_authenticate(u)
        r = self.client.post(reverse("api:evento-list-create"), {
            "categoria_id": CategoriaEvento.objects.create(nombre="X").id, "titulo": "T", "lugar": "L",
            "fecha_evento": (timezone.now() + timedelta(days=3)).isoformat(),
        }, format="json")
        self.assertEqual(r.status_code, 404)
        self.assertEqual(r.data["codigo"], "sin_perfil_organizador")


@override_settings(DEBUG=False)
class PaginasDeErrorTests(TestCase):
    def test_404_usa_la_plantilla_propia(self):
        r = self.client.get("/esta-ruta-no-existe/")
        self.assertEqual(r.status_code, 404)
        self.assertTemplateUsed(r, "404.html")
        self.assertContains(r, "Error 404", status_code=404)

    def test_plantilla_500_renderiza_sin_contexto(self):
        from django.template import loader

        html = loader.get_template("500.html").render()
        self.assertIn("Error 500", html)
