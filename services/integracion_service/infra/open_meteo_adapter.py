"""
Adaptador concreto para la API de terceros de clima (Open-Meteo).

Open-Meteo es una API pública y gratuita que NO requiere API key, ideal para
el requisito "Consumo de API de Terceros vía Patrón Adapter".

Este adaptador implementa el puerto `ProveedorClimaPort`: traduce la respuesta
cruda y específica de Open-Meteo al modelo de dominio `ClimaEvento`, que es el
único formato que conoce el núcleo de la aplicación. Si mañana cambiamos a
OpenWeatherMap o AccuWeather, solo creamos otro adaptador — el resto del
sistema no se entera (Inversión de Dependencias).
"""

from __future__ import annotations

import requests

from domain.ports import ClimaEvento, ProveedorClimaPort

# Mapeo (parcial) de los códigos WMO de Open-Meteo a descripciones legibles.
_WMO = {
    0: "Despejado",
    1: "Mayormente despejado",
    2: "Parcialmente nublado",
    3: "Nublado",
    45: "Niebla",
    51: "Llovizna ligera",
    61: "Lluvia ligera",
    63: "Lluvia moderada",
    65: "Lluvia fuerte",
    80: "Chubascos",
    95: "Tormenta",
}

# Condiciones que consideramos NO aptas para un evento al aire libre.
_CODIGOS_NO_APTOS = {61, 63, 65, 80, 95}


class OpenMeteoAdapter(ProveedorClimaPort):
    """Adaptador: Open-Meteo -> dominio ZonaVip."""

    BASE_URL = "https://api.open-meteo.com/v1/forecast"

    def __init__(self, timeout: float = 5.0):
        self._timeout = timeout

    def obtener_clima(self, ciudad: str, lat: float, lon: float) -> ClimaEvento:
        params = {
            "latitude": lat,
            "longitude": lon,
            "current": "temperature_2m,weather_code",
        }
        respuesta = requests.get(self.BASE_URL, params=params, timeout=self._timeout)
        respuesta.raise_for_status()
        crudo = respuesta.json()

        # --- Traducción del formato EXTERNO al formato de DOMINIO ---
        actual = crudo.get("current", {})
        temperatura = float(actual.get("temperature_2m", 0.0))
        codigo = int(actual.get("weather_code", -1))

        return ClimaEvento(
            ciudad=ciudad,
            temperatura_c=temperatura,
            descripcion=_WMO.get(codigo, "Desconocido"),
            es_apto_aire_libre=codigo not in _CODIGOS_NO_APTOS,
            proveedor="Open-Meteo",
        )
