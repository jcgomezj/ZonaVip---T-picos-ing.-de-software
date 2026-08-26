import os

from infra.notificadores.base import NotificadorBase
from infra.notificadores.consola_notificador import ConsolaNotificador
from infra.notificadores.email_notificador import EmailNotificador


class NotificadorFactory:
    """Patrón Factory Method: gestiona la dependencia externa de notificación.

    El Service (`application/services.py`) nunca pregunta
    `if os.environ["ENV_TYPE"] == "MOCK"`; solo depende de `NotificadorBase`.
    Cambiar de mock a implementación real es un cambio de configuración
    (`ENV_TYPE`), no de código en la capa de aplicación.
    """

    @staticmethod
    def crear() -> NotificadorBase:
        env_type = os.environ.get("ENV_TYPE", "MOCK").upper()

        if env_type == "REAL":
            return EmailNotificador()

        return ConsolaNotificador()
