from infra.notificadores.base import NotificadorBase


class EmailNotificador(NotificadorBase):
    """Adaptador de producción: en una siguiente entrega se conecta a un
    proveedor real (SendGrid, SES, SMTP). Por ahora deja explícito el punto
    de integración sin acoplar el Service Layer a él."""

    def enviar_confirmacion_boleta(self, boleta) -> None:
        destinatario = getattr(boleta.usuario, "email", boleta.usuario_id)
        print(
            f"[EMAIL] Enviando confirmación real de boleta "
            f"(codigo_qr={boleta.codigo_qr}) al usuario {destinatario}"
        )
