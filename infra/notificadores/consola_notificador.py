from infra.notificadores.base import NotificadorBase


class ConsolaNotificador(NotificadorBase):
    """Adaptador de desarrollo/tests: no depende de ningún servicio externo."""

    def enviar_confirmacion_boleta(self, boleta) -> None:
        print(
            f"[DEV-CONSOLA] Boleta reservada. "
            f"codigo_qr={boleta.codigo_qr} | precio={boleta.precio}"
        )
