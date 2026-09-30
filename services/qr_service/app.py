"""
Microservicio de Códigos QR — ZonaVip (Strangler Pattern).

Servicio ligero en Flask que expone, vía API REST/JSON, la funcionalidad
de generación y validación de códigos QR de boletas, estrangulada del
monolito Django. Ver docs/wiki/05-Migracion-a-Microservicios.md.

Contrato de errores estructurado (JSON) para garantizar resiliencia:
    400 -> datos de entrada inválidos / regla de dominio incumplida
    404 -> ruta no encontrada
    405 -> método no permitido
    500 -> error interno no controlado

Todas las respuestas del servicio son `application/json`.
"""

from __future__ import annotations

import logging

from flask import Flask, jsonify, request

from domain.qr_engine import (
    QRDominioError,
    generar_qr,
    nuevo_codigo_qr,
    validar_qr,
)

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("qr_service")


def crear_app() -> Flask:
    """Application Factory: facilita el testing y despliegues con distintas
    configuraciones (mismo patrón Factory que usa el monolito)."""
    app = Flask(__name__)

    # ------------------------------------------------------------------
    # Manejadores de error: contrato JSON uniforme (resiliencia).
    # ------------------------------------------------------------------

    @app.errorhandler(QRDominioError)
    def _manejar_error_dominio(error: QRDominioError):
        return jsonify({"error": str(error), "tipo": "validacion_negocio"}), 400

    @app.errorhandler(400)
    def _bad_request(error):
        return jsonify({"error": "Solicitud inválida.", "tipo": "bad_request"}), 400

    @app.errorhandler(404)
    def _not_found(error):
        return jsonify({"error": "Recurso no encontrado.", "tipo": "not_found"}), 404

    @app.errorhandler(405)
    def _method_not_allowed(error):
        return (
            jsonify({"error": "Método no permitido.", "tipo": "method_not_allowed"}),
            405,
        )

    @app.errorhandler(Exception)
    def _internal_error(error):
        logger.exception("Error interno no controlado en el servicio QR")
        return (
            jsonify({"error": "Error interno del servicio QR.", "tipo": "internal_error"}),
            500,
        )

    # ------------------------------------------------------------------
    # Rutas. Nginx enruta /api/v2/qr/ -> este servicio, por lo que las
    # rutas se declaran bajo ese prefijo para que el ruteo sea transparente.
    # ------------------------------------------------------------------

    @app.get("/api/v2/qr/health")
    def health():
        """Health check para orquestadores (Docker / Nginx upstream)."""
        return jsonify({"servicio": "qr_service", "estado": "ok"}), 200

    @app.post("/api/v2/qr/generar")
    def generar():
        """Genera un QR (PNG base64) a partir de una boleta.

        Body JSON:
            { "boleta_id": <int>, "codigo_qr": "<uuid opcional>" }
        Si no se envía `codigo_qr`, el servicio emite uno nuevo (UUID4).
        """
        datos = request.get_json(silent=True)
        if datos is None or not isinstance(datos, dict):
            raise QRDominioError("Se esperaba un cuerpo JSON válido.")

        boleta_id = datos.get("boleta_id")
        if boleta_id is None:
            raise QRDominioError("El campo 'boleta_id' es obligatorio.")
        try:
            boleta_id = int(boleta_id)
        except (TypeError, ValueError):
            raise QRDominioError("El campo 'boleta_id' debe ser numérico.")

        codigo_qr = datos.get("codigo_qr") or nuevo_codigo_qr()

        resultado = generar_qr(boleta_id, codigo_qr)
        return jsonify(resultado), 201

    @app.post("/api/v2/qr/validar")
    def validar():
        """Valida la firma de un payload de QR emitido por ZonaVip.

        Body JSON: { "payload": "ZONAVIP|<id>|<uuid>|<firma>" }
        """
        datos = request.get_json(silent=True)
        if datos is None or not isinstance(datos, dict):
            raise QRDominioError("Se esperaba un cuerpo JSON válido.")

        payload = datos.get("payload")
        resultado = validar_qr(payload)
        return jsonify(resultado), 200

    return app


# Instancia usada por Gunicorn en el contenedor (app:app).
app = crear_app()


if __name__ == "__main__":
    # Solo para desarrollo local; en el contenedor arranca Gunicorn.
    app.run(host="0.0.0.0", port=5000, debug=True)
