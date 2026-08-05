

import os

from infra.notificadores.base import NotificadorBase
from infra.notificadores.consola_notificador import ConsolaNotificador
from infra.notificadores.email_notificador import EmailNotificador


class NotificadorFactory:
    @staticmethod
    def crear() -> NotificadorBase:
        env_type = os.environ.get("ENV_TYPE", "MOCK").upper()

        if env_type == "REAL":
            return EmailNotificador()


        return ConsolaNotificador()
