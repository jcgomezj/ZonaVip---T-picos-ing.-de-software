"""
Microservicio de Integración — ZonaVip (Entrega 2).

Segundo microservicio estrangulado del monolito. Concentra las
responsabilidades de integración del sistema, exigidas por la Entrega 2:

  1. SERVICIO A PROVEER  -> GET /api/v2/integracion/info
       Expone un endpoint JSON con información relevante del sistema ZonaVip
       (para que el equipo aliado lo consuma).

  2. CONSUMO DE API DE TERCEROS (Patrón Adapter) -> GET /api/v2/integracion/clima
       Consulta el clima de la sede de un evento vía un adaptador
       (Open-Meteo), aplicando Inversión de Dependencias.

  3. CONSUMO DEL EQUIPO ALIADO -> GET /api/v2/integracion/aliado
       Consume el endpoint del equipo aliado (URL por variable de entorno) de
       forma resiliente.

Detrás de Nginx, el prefijo público es /api/v2/integracion/.
Todas las respuestas son application/json con contrato de error estructurado.
"""

from __future__ import annotations

import logging
import os
from datetime import datetime, timezone

from flask import Flask, jsonify, request

from application.services import IntegracionService
from infra.aliado_adapter import AliadoHttpAdapter
from infra.open_meteo_adapter import OpenMeteoAdapter

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("integracion_service")

# Versión del servicio, expuesta en el endpoint de info.
SERVICE_VERSION = "2.0.0"

# Coordenadas por defecto (Medellín) para el pronóstico de clima.
_DEFAULT_LAT = 6.2442
_DEFAULT_LON = -75.5812


def crear_app() -> Flask:
    app = Flask(__name__)

    # --- Composición de dependencias (Inyección manual) -------------------
    # Aquí se "cablean" los adaptadores concretos a los puertos. Es el único
    # lugar que conoce las implementaciones; el resto solo ve interfaces.
    proveedor_clima = OpenMeteoAdapter(timeout=float(os.environ.get("HTTP_TIMEOUT", "5")))
    servicio_aliado = AliadoHttpAdapter(
        base_url=os.environ.get("ALIADO_API_URL", ""),
        timeout=float(os.environ.get("HTTP_TIMEOUT", "5")),
    )
    servicio = IntegracionService(proveedor_clima, servicio_aliado)

    # --- Manejo de errores estructurado (resiliencia) ---------------------

    @app.errorhandler(404)
    def _not_found(_):
        return jsonify({"error": "Recurso no encontrado.", "tipo": "not_found"}), 404

    @app.errorhandler(405)
    def _method(_):
        return jsonify({"error": "Método no permitido.", "tipo": "method_not_allowed"}), 405

    @app.errorhandler(Exception)
    def _internal(error):
        logger.exception("Error interno en el servicio de integración")
        return jsonify({"error": "Error interno del servicio.", "tipo": "internal_error"}), 500

    # --- Rutas ------------------------------------------------------------

    @app.get("/api/v2/integracion/health")
    def health():
        return jsonify({"servicio": "integracion_service", "estado": "ok"}), 200

    @app.get("/api/v2/integracion/info")
    def info():
        """SERVICIO A PROVEER: info del sistema que el aliado puede consumir."""
        return jsonify({
            "sistema": "ZonaVip",
            "descripcion": "Plataforma de reserva de boletas para eventos por localidades.",
            "version": SERVICE_VERSION,
            "arquitectura": "Monolito Django + microservicios Flask (Strangler Pattern)",
            "microservicios": ["qr_service", "integracion_service"],
            "endpoints_publicos": {
                "catalogo_eventos": "/api/v1/eventos/",
                "generar_qr": "/api/v2/qr/generar",
                "clima_sede": "/api/v2/integracion/clima",
            },
            "generado_en": datetime.now(timezone.utc).isoformat(),
        }), 200

    @app.get("/api/v2/integracion/clima")
    def clima():
        """CONSUMO DE TERCEROS (Adapter): clima de la sede de un evento."""
        ciudad = request.args.get("ciudad", "Medellín")
        try:
            lat = float(request.args.get("lat", _DEFAULT_LAT))
            lon = float(request.args.get("lon", _DEFAULT_LON))
        except ValueError:
            return jsonify({"error": "lat/lon deben ser numéricos.", "tipo": "bad_request"}), 400

        return jsonify(servicio.clima_para_sede(ciudad, lat, lon)), 200

    @app.get("/api/v2/integracion/aliado")
    def aliado():
        """CONSUMO DEL ALIADO: proxy resiliente al servicio del equipo aliado."""
        return jsonify(servicio.info_aliado()), 200

    return app


app = crear_app()


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5001, debug=True)
