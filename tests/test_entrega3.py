"""Tests: pagos con idempotencia, reservas con expiración, check-in (USADA),
cancelación de evento con Celery, panel de organizador y permisos."""

from datetime import timedelta
from unittest import mock

from django.contrib.auth import get_user_model
from django.core import mail
from django.test import override_settings
from django.urls import reverse
from django.utils import timezone
from rest_framework.test import APITestCase

from application.services import ExpirarReservasService
from apps.boletas.models import Boleta, Pago
from apps.eventos.models import CategoriaEvento, Evento, Localidad, Organizador
from infra.qr import decodificar_payload, token_dinamico

Usuario = get_user_model()


def _escenario(dias=10, cupo=5):
    org_user = Usuario.objects.create_user(username="org", email="org@x.co", password="x12345678")
    org = Organizador.objects.create(usuario=org_user, nombre_empresarial="Org SAS")
    cat = CategoriaEvento.objects.create(nombre="Concierto")
    ev = Evento.objects.create(
        organizador=org, categoria=cat, titulo="Show", lugar="Estadio",
        fecha_evento=timezone.now() + timedelta(days=dias), estado=Evento.Estado.PUBLICADO,
    )
    loc = Localidad.objects.create(evento=ev, nombre="Norte", precio=100000, cupo=cupo)
    return org_user, ev, loc


def _escenario_extra():
    u = Usuario.objects.create_user(username="org2", password="x12345678")
    org = Organizador.objects.create(usuario=u, nombre_empresarial="Otra")
    ev = Evento.objects.create(
        organizador=org, categoria=CategoriaEvento.objects.first(), titulo="Otro", lugar="Y",
        fecha_evento=timezone.now() + timedelta(days=5), estado=Evento.Estado.PUBLICADO,
    )
    loc = Localidad.objects.create(evento=ev, nombre="L", precio=1, cupo=3)
    return u, ev, loc


class _Base(APITestCase):
    def setUp(self):
        self.org_user, self.ev, self.loc = _escenario()
        self.ana = Usuario.objects.create_user(username="ana", email="ana@x.co", password="clave12345")
        self.staff = Usuario.objects.create_user(username="staff", email="s@x.co", password="clave12345", is_staff=True)
        self.otro = Usuario.objects.create_user(username="otro", email="o@x.co", password="clave12345")
        self.comprar = reverse("api:boleta-comprar")

    def comprar_boletas(self, user=None, n=1, **extra):
        self.client.force_authenticate(user or self.ana)
        return self.client.post(
            self.comprar, {"evento_id": self.ev.id, "localidad_id": self.loc.id, "cantidad": n, **extra}
        )


class PagoTests(_Base):
    def test_compra_crea_pago_aprobado_y_boletas_pagadas(self):
        r = self.comprar_boletas(n=2)
        self.assertEqual(r.status_code, 201, r.content)
        pago = Pago.objects.get()
        self.assertEqual((pago.monto, pago.cantidad, pago.estado), (200000, 2, "APROBADO"))
        self.assertEqual(r.data["pago"]["referencia"], pago.referencia)
        self.assertEqual(Boleta.objects.filter(pago=pago, estado="PAGADA").count(), 2)

    def test_pago_rechazado_devuelve_402_y_no_deja_rastro(self):
        for token in ("tok_declinada", "tok_fondos"):
            r = self.comprar_boletas(token_pago=token)
            self.assertEqual(r.status_code, 402)
            self.assertEqual(r.data["codigo"], "pago_rechazado")
        self.assertEqual((Boleta.objects.count(), Pago.objects.count()), (0, 0))
        self.loc.refresh_from_db()
        self.assertEqual(self.loc.vendidas, 0)

    def test_idempotency_key_evita_doble_cobro(self):
        self.client.force_authenticate(self.ana)
        datos = {"evento_id": self.ev.id, "localidad_id": self.loc.id, "cantidad": 2}
        r1 = self.client.post(self.comprar, datos, HTTP_IDEMPOTENCY_KEY="clave-abc")
        r2 = self.client.post(self.comprar, datos, HTTP_IDEMPOTENCY_KEY="clave-abc")
        self.assertEqual((r1.status_code, r2.status_code), (201, 200))
        self.assertTrue(r2.data["repetida"])
        self.assertEqual(r2["Idempotent-Replayed"], "true")
        self.assertEqual([b["codigo_qr"] for b in r1.data["boletas"]], [b["codigo_qr"] for b in r2.data["boletas"]])
        self.assertEqual((Pago.objects.count(), Boleta.objects.count()), (1, 2))
        self.loc.refresh_from_db()
        self.assertEqual(self.loc.vendidas, 2)

    def test_misma_clave_con_otra_solicitud_es_400(self):
        self.client.force_authenticate(self.ana)
        base = {"evento_id": self.ev.id, "localidad_id": self.loc.id}
        self.client.post(self.comprar, {**base, "cantidad": 1}, HTTP_IDEMPOTENCY_KEY="k1")
        r = self.client.post(self.comprar, {**base, "cantidad": 3}, HTTP_IDEMPOTENCY_KEY="k1")
        self.assertEqual((r.status_code, r.data["codigo"]), (400, "idempotencia_conflicto"))

    def test_la_clave_es_por_usuario(self):
        self.comprar_boletas(HTTP_IDEMPOTENCY_KEY="mismo")
        r = self.comprar_boletas(user=self.otro, HTTP_IDEMPOTENCY_KEY="mismo")
        self.assertEqual(r.status_code, 201)
        self.assertEqual(Pago.objects.count(), 2)

    def test_pago_rechazado_permite_reintentar_con_la_misma_clave(self):
        self.client.force_authenticate(self.ana)
        datos = {"evento_id": self.ev.id, "localidad_id": self.loc.id, "cantidad": 1}
        r1 = self.client.post(self.comprar, {**datos, "token_pago": "tok_fondos"}, HTTP_IDEMPOTENCY_KEY="k")
        r2 = self.client.post(self.comprar, datos, HTTP_IDEMPOTENCY_KEY="k")
        self.assertEqual((r1.status_code, r2.status_code), (402, 201))

    def test_metodo_de_pago_invalido_400(self):
        self.assertEqual(self.comprar_boletas(metodo_pago="BITCOIN").status_code, 400)

    def test_no_se_compra_en_evento_cancelado_ni_pasado(self):
        self.ev.estado = Evento.Estado.CANCELADO
        self.ev.save()
        self.assertEqual(self.comprar_boletas().status_code, 409)
        self.ev.estado = Evento.Estado.PUBLICADO
        self.ev.fecha_evento = timezone.now() - timedelta(hours=1)
        self.ev.save()
        self.assertEqual(self.comprar_boletas().status_code, 409)


class ReservaPagoExpiracionTests(_Base):
    def reservar(self, user=None):
        self.client.force_authenticate(user or self.ana)
        return self.client.post(reverse("api:boleta-reservar"), {"evento_id": self.ev.id, "localidad_id": self.loc.id})

    def test_reserva_tiene_vencimiento_y_se_paga(self):
        r = self.reservar()
        self.assertEqual(r.status_code, 201)
        self.assertIsNotNone(r.data["expira_en"])
        rp = self.client.post(reverse("api:boleta-pagar", args=[r.data["id"]]), {})
        self.assertEqual(rp.status_code, 201, rp.content)
        b = Boleta.objects.get(id=r.data["id"])
        self.assertEqual(b.estado, "PAGADA")
        self.assertIsNone(b.expira_en)
        self.assertEqual(b.pago.monto, 100000)

    def test_pagar_reserva_ajena_403_y_rechazo_402(self):
        bid = self.reservar().data["id"]
        self.client.force_authenticate(self.otro)
        self.assertEqual(self.client.post(reverse("api:boleta-pagar", args=[bid]), {}).status_code, 403)
        self.client.force_authenticate(self.ana)
        r = self.client.post(reverse("api:boleta-pagar", args=[bid]), {"token_pago": "tok_declinada"})
        self.assertEqual(r.status_code, 402)
        self.assertEqual(Boleta.objects.get(id=bid).estado, "RESERVADA")

    def test_pagar_reserva_es_idempotente(self):
        bid = self.reservar().data["id"]
        url = reverse("api:boleta-pagar", args=[bid])
        r1 = self.client.post(url, {}, HTTP_IDEMPOTENCY_KEY="p1")
        r2 = self.client.post(url, {}, HTTP_IDEMPOTENCY_KEY="p1")
        self.assertEqual((r1.status_code, r2.status_code), (201, 200))
        self.assertEqual(Pago.objects.count(), 1)

    def test_tarea_expira_reservas_vencidas_y_libera_cupo(self):
        bid = self.reservar().data["id"]
        vigente = self.reservar(self.otro).data["id"]
        Boleta.objects.filter(id=bid).update(expira_en=timezone.now() - timedelta(minutes=1))
        self.assertEqual(ExpirarReservasService().ejecutar(), 1)
        b = Boleta.objects.get(id=bid)
        self.assertEqual((b.estado, b.motivo_cancelacion), ("CANCELADA", "RESERVA_EXPIRADA"))
        self.assertEqual(Boleta.objects.get(id=vigente).estado, "RESERVADA")
        self.loc.refresh_from_db()
        self.assertEqual(self.loc.vendidas, 1)

    def test_no_se_paga_reserva_vencida(self):
        bid = self.reservar().data["id"]
        Boleta.objects.filter(id=bid).update(expira_en=timezone.now() - timedelta(seconds=1))
        r = self.client.post(reverse("api:boleta-pagar", args=[bid]), {})
        self.assertEqual((r.status_code, r.data["codigo"]), (409, "reserva_vencida"))

    def test_reserva_valida_pertenencia_y_estado_del_evento(self):
        _, otro_ev, _ = _escenario_extra()
        self.client.force_authenticate(self.ana)
        r = self.client.post(reverse("api:boleta-reservar"), {"evento_id": otro_ev.id, "localidad_id": self.loc.id})
        self.assertEqual(r.status_code, 400)
        self.ev.estado = Evento.Estado.BORRADOR
        self.ev.save()
        self.assertEqual(self.reservar().status_code, 409)

    def test_cancelar_boleta_ajena_es_403_y_pagada_reembolsa(self):
        bid = self.comprar_boletas().data["boletas"][0]["id"]
        self.client.force_authenticate(self.otro)
        self.assertEqual(self.client.post(reverse("api:boleta-cancelar", args=[bid])).status_code, 403)
        self.client.force_authenticate(self.ana)
        self.assertEqual(self.client.post(reverse("api:boleta-cancelar", args=[bid])).status_code, 200)
        self.assertEqual(Pago.objects.get().estado, "REEMBOLSADO")
        self.loc.refresh_from_db()
        self.assertEqual(self.loc.vendidas, 0)


class CheckinTests(_Base):
    url = reverse("api:boleta-validar")

    def setUp(self):
        super().setUp()
        self.boleta_id = self.comprar_boletas().data["boletas"][0]["id"]
        self.boleta = Boleta.objects.get(id=self.boleta_id)

    def validar(self, user, codigo=None, **extra):
        self.client.force_authenticate(user)
        return self.client.post(self.url, {"codigo": codigo or self.boleta.codigo_qr, **extra})

    def test_staff_valida_y_boleta_queda_usada(self):
        r = self.validar(self.staff)
        self.assertEqual(r.status_code, 200, r.content)
        self.assertTrue(r.data["valido"])
        self.assertEqual(r.data["boleta"]["estado"], "USADA")
        self.boleta.refresh_from_db()
        self.assertEqual((self.boleta.estado, self.boleta.validada_por), ("USADA", self.staff))
        self.assertIsNotNone(self.boleta.usada_en)

    def test_organizador_del_evento_puede_validar(self):
        self.assertEqual(self.validar(self.org_user).status_code, 200)

    def test_segundo_escaneo_es_409_ya_usada(self):
        self.validar(self.staff)
        r = self.validar(self.staff)
        self.assertEqual((r.status_code, r.data["codigo"]), (409, "ya_usada"))
        self.assertIn("usada_en", r.data)

    def test_asistente_comun_y_organizador_ajeno_reciben_403(self):
        self.assertEqual(self.validar(self.ana).status_code, 403)
        u, _, _ = _escenario_extra()
        self.assertEqual(self.validar(u).status_code, 403)
        self.boleta.refresh_from_db()
        self.assertEqual(self.boleta.estado, "PAGADA")

    def test_anonimo_no_valida(self):
        self.client.force_authenticate(None)
        self.assertIn(self.client.post(self.url, {"codigo": "x"}).status_code, (401, 403))

    def test_codigo_inexistente_404(self):
        r = self.validar(self.staff, "no-existe")
        self.assertEqual((r.status_code, r.data["codigo"]), (404, "boleta_inexistente"))

    def test_reservada_y_cancelada_no_ingresan(self):
        Boleta.objects.filter(id=self.boleta_id).update(estado="RESERVADA")
        self.assertEqual(self.validar(self.staff).data["codigo"], "sin_pago")
        Boleta.objects.filter(id=self.boleta_id).update(estado="CANCELADA")
        self.assertEqual(self.validar(self.staff).data["codigo"], "cancelada")

    def test_qr_dinamico_valido_estatico_y_vencido(self):
        ahora = timezone.now().timestamp()
        vigente = token_dinamico(self.boleta.codigo_qr, ahora=ahora)
        self.assertEqual(decodificar_payload(vigente, ahora=ahora)[1], "dinamico")
        self.assertEqual(decodificar_payload(f"ZV:{self.boleta.codigo_qr}")[1], "estatico")
        viejo = token_dinamico(self.boleta.codigo_qr, ahora=ahora - 3600)
        r = self.validar(self.staff, viejo)
        self.assertEqual((r.status_code, r.data["codigo"]), (400, "qr_invalido"))
        self.assertEqual(self.validar(self.staff, vigente).status_code, 200)

    def test_firma_manipulada_es_rechazada(self):
        t = token_dinamico(self.boleta.codigo_qr, ahora=timezone.now().timestamp())
        self.assertEqual(self.validar(self.staff, t[:-3] + "xxx").status_code, 400)

    @override_settings(CHECKIN_EXIGIR_QR_DINAMICO=True)
    def test_modo_estricto_rechaza_codigo_estatico(self):
        self.assertEqual(self.validar(self.staff, f"ZV:{self.boleta.codigo_qr}").data["codigo"], "qr_no_dinamico")

    def test_puerta_de_otro_evento_se_rechaza(self):
        _, otro_ev, _ = _escenario_extra()
        r = self.validar(self.staff, evento_id=otro_ev.id)
        self.assertEqual((r.status_code, r.data["codigo"]), (409, "otro_evento"))

    def test_ingreso_cerrado_tras_el_evento(self):
        Evento.objects.filter(id=self.ev.id).update(fecha_evento=timezone.now() - timedelta(days=3))
        self.assertEqual(self.validar(self.staff).data["codigo"], "fuera_de_horario")

    @override_settings(CHECKIN_APERTURA_HORAS_ANTES=2)
    def test_apertura_configurable(self):
        self.assertEqual(self.validar(self.staff).data["codigo"], "fuera_de_horario")

    def test_boleta_usada_no_se_puede_cancelar(self):
        self.validar(self.staff)
        self.client.force_authenticate(self.ana)
        self.assertEqual(self.client.post(reverse("api:boleta-cancelar", args=[self.boleta_id])).status_code, 409)

    def test_pantalla_de_checkin_solo_staff_u_organizador(self):
        c = self.client_class()
        self.assertEqual(c.get(reverse("web:checkin")).status_code, 302)
        c.force_login(self.ana)
        self.assertEqual(c.get(reverse("web:checkin")).status_code, 404)
        c.force_login(self.staff)
        self.assertEqual(c.get(reverse("web:checkin")).status_code, 200)
        c.force_login(self.org_user)
        self.assertContains(c.get(reverse("web:checkin")), "Show")


class CancelarEventoTests(_Base):
    def cancelar(self, user, motivo="Lluvia"):
        self.client.force_authenticate(user)
        return self.client.post(reverse("api:evento-cancelar", args=[self.ev.id]), {"motivo": motivo})

    def test_cancela_boletas_libera_cupo_reembolsa_y_notifica(self):
        self.comprar_boletas(n=2)
        self.comprar_boletas(user=self.otro, n=1)
        mail.outbox.clear()
        reserva = self.client.post(
            reverse("api:boleta-reservar"), {"evento_id": self.ev.id, "localidad_id": self.loc.id}
        ).data["id"]
        with self.captureOnCommitCallbacks(execute=True):
            r = self.cancelar(self.org_user)
        self.assertEqual(r.status_code, 200, r.content)
        self.assertEqual(r.data["boletas_canceladas"], 4)
        self.assertEqual(r.data["monto_reembolsado"], "300000.00")
        self.ev.refresh_from_db()
        self.assertEqual(self.ev.estado, "CANCELADO")
        self.assertFalse(Boleta.objects.exclude(estado="CANCELADA").exists())
        self.assertEqual(Boleta.objects.filter(motivo_cancelacion="EVENTO_CANCELADO").count(), 4)
        self.loc.refresh_from_db()
        self.assertEqual(self.loc.vendidas, 0)
        self.assertEqual(set(Pago.objects.values_list("estado", flat=True)), {"REEMBOLSADO"})
        self.assertEqual(len(mail.outbox), 2)  # Celery eager: un correo por usuario
        self.assertTrue(all("Evento cancelado" in m.subject for m in mail.outbox))
        self.assertIn("Lluvia", mail.outbox[0].body)
        self.assertEqual(Boleta.objects.get(id=reserva).estado, "CANCELADA")

    def test_boletas_usadas_se_respetan(self):
        bid = self.comprar_boletas(n=2).data["boletas"][0]["id"]
        self.client.force_authenticate(self.staff)
        self.client.post(reverse("api:boleta-validar"), {"codigo": Boleta.objects.get(id=bid).codigo_qr})
        r = self.cancelar(self.staff)
        self.assertEqual(r.data["boletas_canceladas"], 1)
        self.assertEqual(Boleta.objects.get(id=bid).estado, "USADA")
        self.assertEqual(Pago.objects.get().estado, "APROBADO")

    def test_solo_el_organizador_del_evento_o_admin(self):
        self.assertEqual(self.cancelar(self.ana).status_code, 403)
        u, _, _ = _escenario_extra()
        self.assertEqual(self.cancelar(u).status_code, 403)
        self.ev.refresh_from_db()
        self.assertEqual(self.ev.estado, "PUBLICADO")
        self.assertEqual(self.cancelar(self.staff).status_code, 200)

    def test_no_se_cancela_dos_veces_y_evento_cancelado_no_vende(self):
        self.assertEqual(self.cancelar(self.org_user).status_code, 200)
        self.assertEqual(self.cancelar(self.org_user).status_code, 409)
        self.assertEqual(self.comprar_boletas().status_code, 409)

    def test_si_el_broker_falla_la_cancelacion_no_se_deshace(self):
        self.comprar_boletas()
        with mock.patch("apps.reportes.tasks.notificar_cancelacion_evento.delay",
                        side_effect=ConnectionError("redis caído")):
            with self.captureOnCommitCallbacks(execute=True):
                r = self.cancelar(self.org_user)
        self.assertEqual(r.status_code, 200)
        self.ev.refresh_from_db()
        self.assertEqual(self.ev.estado, "CANCELADO")

    def test_boleta_cancelada_por_evento_aparece_en_historial_del_perfil(self):
        self.comprar_boletas()
        self.cancelar(self.org_user)
        c = self.client_class()
        c.force_login(self.ana)
        r = c.get(reverse("web:perfil"))
        self.assertEqual(len(r.context["historial"]), 1)
        self.assertContains(r, "EVENTO CANCELADO")


class OrganizadorPanelTests(_Base):
    def test_resumen_por_localidad_y_ocupacion(self):
        Localidad.objects.create(evento=self.ev, nombre="VIP", precio=500000, cupo=10)
        self.comprar_boletas(n=3)
        bid = self.comprar_boletas(user=self.otro, n=1).data["boletas"][0]["id"]
        self.client.force_authenticate(self.staff)
        self.client.post(reverse("api:boleta-validar"), {"codigo": Boleta.objects.get(id=bid).codigo_qr})
        self.client.force_authenticate(self.org_user)
        r = self.client.get(reverse("api:organizador-resumen"))
        self.assertEqual(r.status_code, 200)
        ev = r.data["eventos"][0]
        norte = next(l for l in ev["localidades"] if l["nombre"] == "Norte")
        self.assertEqual((norte["vendidas"], norte["cupo"], norte["ocupacion_pct"]), (4, 5, 80))
        self.assertEqual((norte["pagadas"], norte["usadas"]), (3, 1))
        self.assertEqual(norte["ingresos"], 400000.0)
        self.assertEqual(ev["ocupacion_pct"], round(4 * 100 / 15))
        self.assertEqual(ev["asistencia_pct"], 25)
        self.assertEqual(r.data["totales"]["ingresos"], 400000.0)

    def test_organizador_solo_ve_sus_eventos_y_usuario_comun_403(self):
        _escenario_extra()
        self.client.force_authenticate(self.org_user)
        self.assertEqual([e["titulo"] for e in self.client.get(reverse("api:organizador-resumen")).data["eventos"]], ["Show"])
        self.client.force_authenticate(self.staff)
        self.assertEqual(len(self.client.get(reverse("api:organizador-resumen")).data["eventos"]), 2)
        self.client.force_authenticate(self.ana)
        self.assertEqual(self.client.get(reverse("api:organizador-resumen")).status_code, 403)

    def test_numero_de_consultas_no_crece_con_las_boletas(self):
        from django.db import connection
        from django.test.utils import CaptureQueriesContext

        from application.queries import resumen_organizador

        with CaptureQueriesContext(connection) as base:
            resumen_organizador()
        self.comprar_boletas(n=4)
        with CaptureQueriesContext(connection) as con_ventas:
            resumen_organizador()
        self.assertEqual(len(base), len(con_ventas))

    def test_pagina_web_y_cancelacion_desde_el_panel(self):
        self.comprar_boletas()
        c = self.client_class()
        c.force_login(self.ana)
        self.assertEqual(c.get(reverse("web:organizador")).status_code, 404)
        c.force_login(self.org_user)
        r = c.get(reverse("web:organizador"))
        self.assertContains(r, "Show")
        self.assertContains(r, "Norte")
        with self.captureOnCommitCallbacks(execute=True):
            r = c.post(reverse("web:organizador-cancelar-evento", args=[self.ev.id]), {"motivo": "x"})
        self.assertRedirects(r, reverse("web:organizador"))
        self.ev.refresh_from_db()
        self.assertEqual(self.ev.estado, "CANCELADO")
        self.assertEqual(c.get(reverse("web:organizador-cancelar-evento", args=[self.ev.id])).status_code, 405)


class PermisosEntrega2Tests(_Base):
    def test_reportes_notificaciones_y_tareas_solo_admin(self):
        endpoints = [("post", "/api/v1/reportes/ventas/", {}),
                     ("post", "/api/v1/notificaciones/", {"mensaje": "hola"}),
                     ("get", "/api/v1/tareas/abc/", None)]
        for metodo, url, datos in endpoints:
            llamar = lambda: (self.client.post(url, datos) if metodo == "post" else self.client.get(url))
            self.client.force_authenticate(None)
            self.assertIn(llamar().status_code, (401, 403), url)
            self.client.force_authenticate(self.ana)
            self.assertEqual(llamar().status_code, 403, url)

    def test_notificacion_valida_entradas_en_vez_de_500(self):
        self.client.force_authenticate(self.staff)
        for cuerpo in ({"mensaje": "x", "destinatarios": "abc"}, {"mensaje": 123456, "destinatarios": 0}, {}):
            self.assertEqual(self.client.post("/api/v1/notificaciones/", cuerpo).status_code, 400, cuerpo)

    def test_health(self):
        r = self.client.get("/health/")
        self.assertEqual((r.status_code, r.json()["estado"]), (200, "ok"))
