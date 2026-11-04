import os

from infra.pagos.base import PasarelaPagoBase
from infra.pagos.pasarela_simulada import PasarelaSimulada


class PasarelaPagoFactory:
    """Factory Method (igual que NotificadorFactory). PAGOS_MODE=SIMULADO por
    defecto; para un proveedor real: otra subclase de PasarelaPagoBase."""

    @staticmethod
    def crear() -> PasarelaPagoBase:
        if os.environ.get("PAGOS_MODE", "SIMULADO").upper() == "REAL":
            raise NotImplementedError("PAGOS_MODE=REAL: aún no hay adaptador real.")
        return PasarelaSimulada()
