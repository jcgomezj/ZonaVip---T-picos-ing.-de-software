"""Tests del flujo web: compra autenticada, correo, perfil, panel solo admin."""

from django.contrib.auth import get_user_model
from django.core import mail
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone
from rest_framework.test import APITestCase

from apps.boletas.models import Boleta
from apps.eventos.models import CategoriaEvento, Evento, Localidad, Organizador
from infra.qr import token_dinamico, token_valido

Usuario = get_user_model()


def _evento(recinto=Evento.TipoRecinto.ESTADIO):
    org_user = Usuario.objects.create_user(username="org", password="x12345678")
    org = Organizador.objects.create(usuario=org_user, nombre_empresarial="Org")
    cat = CategoriaEvento.objects.create(nombre="Concierto")
    ev = Evento.objects.create(
        organizador=org, categoria=cat, titulo="Show", lugar="Atanasio Girardot",
        fecha_evento=timezone.now() + timezone.timedelta(days=10),
        estado=Evento.Estado.PUBLICADO, tipo_recinto=recinto,
    )
    loc = Localidad.objects.create(evento=ev, nombre="Norte", precio=100000, cupo=5)
    return ev, loc


class CompraAPITests(APITestCase):
    def setUp(self):
        self.ev, self.loc = _evento()
        self.user = Usuario.objects.create_user(
            username="ana", email="ana@correo.com", password="clave12345"
        )
        self.url = reverse("api:boleta-comprar")

    def test_anonimo_no_puede_comprar(self):
        r = self.client.post(self.url, {"evento_id": self.ev.id, "localidad_id": self.loc.id, "cantidad": 1})
        self.assertIn(r.status_code, (401, 403))
        self.assertEqual(Boleta.objects.count(), 0)

    def test_compra_multiple_envia_correo_con_qr(self):
        self.client.force_authenticate(self.user)
        with self.captureOnCommitCallbacks(execute=True):
            r = self.client.post(
                self.url, {"evento_id": self.ev.id, "localidad_id": self.loc.id, "cantidad": 3}
            )
        self.assertEqual(r.status_code, 201, r.content)
        self.assertEqual(Boleta.objects.filter(usuario=self.user, estado="PAGADA").count(), 3)
        self.loc.refresh_from_db()
        self.assertEqual(self.loc.vendidas, 3)
        self.assertEqual(len(mail.outbox), 1)
        correo = mail.outbox[0]
        self.assertEqual(correo.to, ["ana@correo.com"])
        self.assertIn("Total pagado", correo.body)
        self.assertEqual(len([a for a in correo.attachments if "image" in str(a.get_content_type())]), 3)

    def test_no_permite_exceder_cupo(self):
        self.client.force_authenticate(self.user)
        r = self.client.post(self.url, {"evento_id": self.ev.id, "localidad_id": self.loc.id, "cantidad": 6})
        self.assertEqual(r.status_code, 409)
        self.assertEqual(Boleta.objects.count(), 0)

    def test_localidad_de_otro_evento_rechazada(self):
        self.client.force_authenticate(self.user)
        r = self.client.post(self.url, {"evento_id": self.ev.id + 99, "localidad_id": self.loc.id, "cantidad": 1})
        self.assertEqual(r.status_code, 400)


class AccesoWebTests(TestCase):
    def setUp(self):
        self.user = Usuario.objects.create_user(username="ana", email="a@a.co", password="clave12345")
        self.admin = Usuario.objects.create_user(
            username="root", email="r@r.co", password="clave12345", is_staff=True
        )

    def test_panel_oculto_para_usuario_comun(self):
        self.client.force_login(self.user)
        self.assertEqual(self.client.get(reverse("web:panel")).status_code, 404)
        self.assertNotContains(self.client.get(reverse("web:home")), "Panel del sistema")

    def test_panel_visible_para_admin(self):
        self.client.force_login(self.admin)
        self.assertEqual(self.client.get(reverse("web:panel")).status_code, 200)
        self.assertContains(self.client.get(reverse("web:home")), "Panel del sistema")

    def test_panel_anonimo_redirige_a_login(self):
        r = self.client.get(reverse("web:panel"))
        self.assertEqual(r.status_code, 302)
        self.assertIn(reverse("web:login"), r["Location"])

    def test_panel_sin_etiquetas_tecnicas(self):
        self.client.force_login(self.admin)
        html = self.client.get(reverse("web:panel")).content.decode()
        for texto in ("Patrón Adapter", "Message Broker", "Celery", "API de terceros", "Información del sistema"):
            self.assertNotIn(texto, html)

    def test_login_sin_credenciales_expuestas(self):
        html = self.client.get(reverse("web:login")).content.decode()
        self.assertNotIn("zonavip2026", html)
        self.assertNotIn("Credenciales de prueba", html)

    def test_registro_inicia_sesion_y_respeta_next(self):
        r = self.client.post(reverse("web:registro"), {
            "username": "nuevo", "email": "n@n.co", "password1": "Clave-segura-987", "password2": "Clave-segura-987",
            "next": "/?comprar=3",
        })
        self.assertRedirects(r, "/?comprar=3", fetch_redirect_response=False)
        nuevo = Usuario.objects.get(username="nuevo")
        self.assertFalse(nuevo.is_staff)
        self.assertEqual(int(self.client.session["_auth_user_id"]), nuevo.pk)

    def test_perfil_tiene_exactamente_dos_vencidas(self):
        self.client.force_login(self.user)
        r = self.client.get(reverse("web:perfil"))
        self.assertEqual(len(r.context["vencidas"]), 2)

    def test_qr_dinamico_solo_para_el_dueno(self):
        ev, loc = _evento()
        b = Boleta.objects.create(
            usuario=self.user, evento=ev, localidad=loc, codigo_qr="abc-123",
            precio=1, estado="PAGADA", reservada_en=timezone.now(),
        )
        self.client.force_login(self.user)
        r = self.client.get(reverse("web:qr-boleta", args=[b.codigo_qr]))
        self.assertEqual((r.status_code, r["Content-Type"]), (200, "image/png"))
        self.client.force_login(self.admin)
        self.assertEqual(self.client.get(reverse("web:qr-boleta", args=[b.codigo_qr])).status_code, 404)

    def test_token_dinamico_expira(self):
        t = token_dinamico("abc", ahora=1000)
        self.assertTrue(token_valido(t, ahora=1010))
        self.assertFalse(token_valido(t, ahora=1000 + 300))
