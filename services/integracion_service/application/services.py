"""
Capa de aplicación del microservicio de integración.

Orquesta los puertos (clima de terceros, servicio del aliado) sin conocer sus
implementaciones concretas: los recibe inyectados en el constructor. Esto es
Inversión de Dependencias aplicada — el mismo principio que el monolito usa en
`application/services.py` con sus Repositorios y el `NotificadorFactory`.
"""

from __future__ import annotations

from dataclasses import asdict

from domain.ports import ProveedorClimaPort, ServicioAliadoPort


class IntegracionService:
    def __init__(
        self,
        proveedor_clima: ProveedorClimaPort,
        servicio_aliado: ServicioAliadoPort,
    ):
        self._clima = proveedor_clima
        self._aliado = servicio_aliado

    def clima_para_sede(self, ciudad: str, lat: float, lon: float) -> dict:
        """Consumo de API de terceros vía Adapter -> dict JSON-serializable."""
        return asdict(self._clima.obtener_clima(ciudad, lat, lon))

    def info_aliado(self) -> dict:
        """Consumo del servicio del equipo aliado -> dict JSON-serializable."""
        return asdict(self._aliado.obtener_info())
