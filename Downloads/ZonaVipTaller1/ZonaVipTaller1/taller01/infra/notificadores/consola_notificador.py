

from infra.notificadores.base import NotificadorBase


class ConsolaNotificador(NotificadorBase):
    def enviar_confirmacion_boleta(self, boleta) -> None:
        print(
            f"[DEV-CONSOLA] Boleta reservada. "
            f"codigo_qr={boleta.codigo_qr} | precio={boleta.precio}"
        )
