"""
Adaptador para consumir el servicio del EQUIPO ALIADO.

Implementa `ServicioAliadoPort`. La URL del aliado se inyecta por variable de
entorno (`ALIADO_API_URL`), de modo que cuando el equipo aliado publique su
endpoint real, solo cambia la configuración — no el código.

Es resiliente: si el aliado no responde (timeout, 5xx, red caída), NO propaga
la excepción hacia arriba; devuelve `InfoAliado(disponible=False, ...)` para
que la UI pueda degradar con elegancia en vez de romperse. Esto materializa el
atributo de calidad "Resiliencia" de la rúbrica.
"""

from __future__ import annotations

import requests

from domain.ports import InfoAliado, ServicioAliadoPort


class AliadoHttpAdapter(ServicioAliadoPort):
    def __init__(self, base_url: str, timeout: float = 5.0):
        self._base_url = base_url.rstrip("/")
        self._timeout = timeout

    def obtener_info(self) -> InfoAliado:
        if not self._base_url:
            return InfoAliado(
                disponible=False,
                datos={},
                fuente="(no configurado)",
                error="No se configuró ALIADO_API_URL.",
            )

        try:
            respuesta = requests.get(self._base_url, timeout=self._timeout)
            respuesta.raise_for_status()
            return InfoAliado(
                disponible=True,
                datos=respuesta.json(),
                fuente=self._base_url,
            )
        except requests.exceptions.RequestException as exc:
            # Resiliencia: degradar con elegancia, nunca tumbar nuestra app
            # porque un servicio externo falle.
            return InfoAliado(
                disponible=False,
                datos={},
                fuente=self._base_url,
                error=f"El servicio aliado no está disponible: {exc}",
            )
