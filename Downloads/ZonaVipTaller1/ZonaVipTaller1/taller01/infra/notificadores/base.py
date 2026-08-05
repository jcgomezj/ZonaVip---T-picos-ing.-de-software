

from abc import ABC, abstractmethod


class NotificadorBase(ABC):
    @abstractmethod
    def enviar_confirmacion_boleta(self, boleta) -> None:
        raise NotImplementedError
