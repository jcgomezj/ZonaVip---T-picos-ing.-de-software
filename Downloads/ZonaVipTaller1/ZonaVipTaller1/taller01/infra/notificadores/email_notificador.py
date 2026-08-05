

from infra.notificadores.base import NotificadorBase


class EmailNotificador(NotificadorBase):
    def enviar_confirmacion_boleta(self, boleta) -> None:

        destinatario = boleta.usuario_id  # en la práctica: boleta.usuario.email
        print(
            f"[EMAIL] Enviando confirmación real de boleta "
            f"(codigo_qr={boleta.codigo_qr}) al usuario {destinatario}"
        )
