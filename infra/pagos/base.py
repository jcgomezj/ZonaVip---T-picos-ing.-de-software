"""Puerto de salida de pagos (Dependency Inversion)."""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
from decimal import Decimal


@dataclass(frozen=True)
class ResultadoCobro:
    aprobado: bool
    referencia: str
    motivo: str = ""


class PasarelaPagoBase(ABC):
    @abstractmethod
    def cobrar(self, monto: Decimal, metodo: str, token: str) -> ResultadoCobro:
        """Cobra `monto`. Los rechazos de negocio NO lanzan: aprobado=False."""
        raise NotImplementedError

    @abstractmethod
    def reembolsar(self, referencia: str, monto: Decimal) -> bool:
        raise NotImplementedError
