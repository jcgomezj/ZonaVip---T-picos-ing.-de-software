"""
Generación local de códigos QR (sin depender de servicios externos).

- `png_qr_estatico(codigo)`: QR fijo, para el correo de confirmación.
- `token_dinamico(codigo)`: payload firmado que cambia cada ventana de
  `VENTANA_SEGUNDOS`; el perfil recarga el QR periódicamente, de modo que una
  captura de pantalla vieja deja de ser válida (QR "dinámico").
"""

from __future__ import annotations

import hashlib
import hmac
import io
import time

import qrcode
from django.conf import settings

VENTANA_SEGUNDOS = 30


def _png(payload: str) -> bytes:
    qr = qrcode.QRCode(box_size=8, border=2)
    qr.add_data(payload)
    qr.make(fit=True)
    buf = io.BytesIO()
    qr.make_image(fill_color="black", back_color="white").save(buf, format="PNG")
    return buf.getvalue()


def png_qr_estatico(codigo: str) -> bytes:
    return _png(f"ZV:{codigo}")


def _firma(codigo: str, ventana: int) -> str:
    msg = f"{codigo}:{ventana}".encode()
    return hmac.new(settings.SECRET_KEY.encode(), msg, hashlib.sha256).hexdigest()[:12]


def token_dinamico(codigo: str, ahora: float | None = None) -> str:
    ventana = int((ahora if ahora is not None else time.time()) // VENTANA_SEGUNDOS)
    return f"ZV:{codigo}:{ventana}:{_firma(codigo, ventana)}"


def token_valido(token: str, ahora: float | None = None) -> bool:
    try:
        _, codigo, ventana, firma = token.split(":")
        ventana_i = int(ventana)
    except ValueError:
        return False
    actual = int((ahora if ahora is not None else time.time()) // VENTANA_SEGUNDOS)
    return abs(actual - ventana_i) <= 1 and hmac.compare_digest(firma, _firma(codigo, ventana_i))


def png_qr_dinamico(codigo: str) -> bytes:
    return _png(token_dinamico(codigo))
