"""Pasarela de pagos SIMULADA (modo pruebas). No mueve dinero ni guarda
tarjetas: recibe un `token` opaco y decide por su valor.

    tok_ok (o vacío) -> aprobado
    tok_declinada    -> tarjeta declinada
    tok_fondos       -> fondos insuficientes
    tok_error        -> error temporal de la pasarela
"""

from __future__ import annotations

import uuid
from decimal import Decimal

from infra.pagos.base import PasarelaPagoBase, ResultadoCobro

METODOS_VALIDOS = ("TARJETA", "PSE", "NEQUI")

_RECHAZOS = {
    "tok_declinada": "La tarjeta fue declinada por el banco emisor.",
    "tok_fondos": "Fondos insuficientes.",
    "tok_error": "La pasarela de pagos no está disponible. Inténtalo de nuevo.",
}


class PasarelaSimulada(PasarelaPagoBase):
    def cobrar(self, monto: Decimal, metodo: str, token: str) -> ResultadoCobro:
        if monto <= 0:
            return ResultadoCobro(False, "", "El monto a cobrar debe ser positivo.")
        token = (token or "tok_ok").strip().lower()
        if token in _RECHAZOS:
            return ResultadoCobro(False, "", _RECHAZOS[token])
        return ResultadoCobro(True, f"SIM-{uuid.uuid4().hex[:16].upper()}")

    def reembolsar(self, referencia: str, monto: Decimal) -> bool:
        return bool(referencia)
