from abc import ABC, abstractmethod


class NotificadorBase(ABC):
    """Puerto de salida: el Service Layer solo conoce esta interfaz,
    nunca una implementación concreta (Dependency Inversion Principle)."""

    @abstractmethod
    def enviar_confirmacion_boleta(self, boleta) -> None:
        raise NotImplementedError
