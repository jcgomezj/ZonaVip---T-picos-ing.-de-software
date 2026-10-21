"""
Puertos (interfaces abstractas) del microservicio de integración.

Aquí vive la **Inversión de Dependencias (DIP)**: el núcleo de la aplicación
depende de estas abstracciones, nunca de una implementación concreta (una API
de terceros, el servicio de un equipo aliado, etc.). Los adaptadores concretos
que implementan estos puertos viven en `infra/` y se inyectan desde afuera.

Esto es la base del **Patrón Adapter** exigido por la Entrega 2: podemos
cambiar el proveedor de clima o la URL del aliado sin tocar la lógica de
negocio, solo cambiando el adaptador o su configuración.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Optional


# ---------------------------------------------------------------------------
# Modelos de dominio (DTOs): el vocabulario propio de ZonaVip, independiente
# del formato que devuelva cada proveedor externo.
# ---------------------------------------------------------------------------


@dataclass
class ClimaEvento:
    """Pronóstico del clima para la sede de un evento, en el formato propio
    de ZonaVip (no en el formato crudo del proveedor externo)."""

    ciudad: str
    temperatura_c: float
    descripcion: str
    es_apto_aire_libre: bool
    proveedor: str


@dataclass
class InfoAliado:
    """Información cruda recibida del equipo aliado (contrato flexible)."""

    disponible: bool
    datos: dict
    fuente: str
    error: Optional[str] = None


# ---------------------------------------------------------------------------
# Puertos
# ---------------------------------------------------------------------------


class ProveedorClimaPort(ABC):
    """Puerto de salida hacia una API de terceros de clima.

    El núcleo depende de ESTA interfaz; el adaptador concreto
    (`infra/open_meteo_adapter.py`) traduce la respuesta cruda del proveedor
    al modelo de dominio `ClimaEvento`."""

    @abstractmethod
    def obtener_clima(self, ciudad: str, lat: float, lon: float) -> ClimaEvento:
        raise NotImplementedError


class ServicioAliadoPort(ABC):
    """Puerto de salida hacia el servicio expuesto por el equipo aliado."""

    @abstractmethod
    def obtener_info(self) -> InfoAliado:
        raise NotImplementedError
