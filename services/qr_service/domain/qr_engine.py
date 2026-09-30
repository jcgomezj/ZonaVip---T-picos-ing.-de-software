"""
Núcleo de dominio del microservicio de QR.

Este módulo NO conoce Flask ni HTTP: es lógica pura y testeable. Encapsula
las dos responsabilidades que se estrangularon del monolito Django:

    1. Generar la representación de un código QR para una boleta
       (operación CPU-intensiva: renderizado de la matriz + PNG en base64).
    2. Validar/decodificar la firma de un código QR emitido por ZonaVip.

Mantener esta lógica aislada del framework es lo que permite reemplazar
Flask por otra tecnología en el futuro sin reescribir el negocio, en la
misma filosofía de capas que ya usa el monolito.
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import io
import os
import time
import uuid

import qrcode

# Secreto compartido para firmar los QR. En producción se inyecta por
# variable de entorno; nunca se hardcodea la clave real en el código.
_QR_SECRET = os.environ.get("QR_SECRET", "zonavip-qr-dev-secret").encode("utf-8")

# Prefijo del payload textual que se codifica dentro del QR.
_PAYLOAD_PREFIX = "ZONAVIP"


class QRDominioError(Exception):
    """Error de reglas de negocio del dominio QR (se traduce a HTTP 400)."""


def _firmar(payload: str) -> str:
    """Devuelve una firma HMAC-SHA256 truncada del payload."""
    firma = hmac.new(_QR_SECRET, payload.encode("utf-8"), hashlib.sha256)
    return firma.hexdigest()[:16]


def construir_payload(boleta_id: int, codigo_qr: str) -> str:
    """Construye el texto firmado que viajará dentro del QR.

    Formato: ZONAVIP|<boleta_id>|<codigo_qr>|<firma>
    """
    if not isinstance(boleta_id, int) or boleta_id <= 0:
        raise QRDominioError("El 'boleta_id' debe ser un entero positivo.")
    if not codigo_qr or not str(codigo_qr).strip():
        raise QRDominioError("El 'codigo_qr' es obligatorio y no puede estar vacío.")

    base = f"{_PAYLOAD_PREFIX}|{boleta_id}|{codigo_qr}"
    return f"{base}|{_firmar(base)}"


def generar_qr(boleta_id: int, codigo_qr: str) -> dict:
    """Genera un QR (PNG base64) a partir de los datos mínimos de una boleta.

    Devuelve un diccionario listo para serializar a JSON. Es la operación
    "pesada" que se extrajo del monolito: el render de la imagen ya no
    bloquea el hilo de Django.
    """
    payload = construir_payload(boleta_id, codigo_qr)

    inicio = time.perf_counter()
    qr = qrcode.QRCode(
        version=None,
        error_correction=qrcode.constants.ERROR_CORRECT_M,
        box_size=8,
        border=2,
    )
    qr.add_data(payload)
    qr.make(fit=True)
    imagen = qr.make_image(fill_color="black", back_color="white")

    buffer = io.BytesIO()
    imagen.save(buffer, format="PNG")
    png_base64 = base64.b64encode(buffer.getvalue()).decode("ascii")
    duracion_ms = round((time.perf_counter() - inicio) * 1000, 2)

    return {
        "boleta_id": boleta_id,
        "codigo_qr": codigo_qr,
        "payload": payload,
        "imagen_base64": f"data:image/png;base64,{png_base64}",
        "formato": "PNG",
        "generado_en_ms": duracion_ms,
    }


def validar_qr(payload: str) -> dict:
    """Valida un payload de QR emitido por ZonaVip verificando su firma HMAC.

    Devuelve el resultado de la validación. No lanza si la firma es inválida:
    devuelve `valido=False`, porque "firma incorrecta" es una respuesta de
    negocio esperada, no un error del servicio.
    """
    if not payload or not str(payload).strip():
        raise QRDominioError("El 'payload' es obligatorio para validar un QR.")

    partes = payload.split("|")
    if len(partes) != 4 or partes[0] != _PAYLOAD_PREFIX:
        return {
            "valido": False,
            "motivo": "El formato del payload no corresponde a un QR de ZonaVip.",
        }

    _, boleta_id, codigo_qr, firma_recibida = partes
    base = f"{_PAYLOAD_PREFIX}|{boleta_id}|{codigo_qr}"
    firma_esperada = _firmar(base)

    if not hmac.compare_digest(firma_recibida, firma_esperada):
        return {
            "valido": False,
            "motivo": "La firma del QR no es válida (posible falsificación).",
        }

    return {
        "valido": True,
        "boleta_id": int(boleta_id) if boleta_id.isdigit() else boleta_id,
        "codigo_qr": codigo_qr,
    }


def nuevo_codigo_qr() -> str:
    """Genera un identificador único (UUID4) para una boleta nueva.

    Réplica exacta de `BoletaBuilder.generar_codigo_qr()` del monolito, para
    que el microservicio también pueda emitir el identificador base del QR.
    """
    return str(uuid.uuid4())
