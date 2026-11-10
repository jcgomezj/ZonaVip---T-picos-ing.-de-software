"""
Vistas de la API para las funcionalidades nuevas de la Entrega 2:

  - Tareas asíncronas (Celery + Redis): disparar y consultar reportes /
    notificaciones en segundo plano.
  - Proxy al microservicio de integración (info del sistema, clima, aliado),
    para que el frontend consuma todo a través del mismo origen (vía Nginx).

Igual que el resto de la API, estas vistas son delgadas: delegan en Celery o
en el microservicio y traducen el resultado a HTTP/JSON.
"""

from __future__ import annotations

import logging

import requests
from celery.result import AsyncResult
from django.conf import settings
from rest_framework import status
from rest_framework.permissions import IsAdminUser
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.reportes.tasks import (
    enviar_notificacion_masiva,
    generar_reporte_ventas,
)

from .serializers import NotificacionMasivaInputSerializer, ReporteVentasInputSerializer

logger = logging.getLogger(__name__)


def _encolar(tarea, *args):
    """Encola en Celery fallando rápido si el broker (Redis) no responde.

    Con `.delay()` Celery reintenta la conexión indefinidamente y la petición
    se queda colgada hasta el timeout de Gunicorn/Nginx (502). Aquí se
    devuelve un 503 claro y uniforme en su lugar."""
    try:
        resultado = tarea.apply_async(args=args, retry=False)
    except Exception:  # noqa: BLE001 - cualquier fallo del broker
        logger.exception("No se pudo encolar la tarea %s", tarea.name)
        return None, Response(
            {"error": "El servicio de tareas en segundo plano no está disponible.",
             "codigo": "broker_no_disponible"},
            status=status.HTTP_503_SERVICE_UNAVAILABLE,
        )
    return resultado, Response(
        {
            "task_id": resultado.id,
            "estado": "encolado",
            "consultar_en": f"/api/v1/tareas/{resultado.id}/",
        },
        status=status.HTTP_202_ACCEPTED,
    )


class GenerarReporteView(APIView):
    """POST /api/v1/reportes/ventas/ -> encola el reporte en Celery (asíncrono).

    Devuelve 202 Accepted + un task_id para consultar el resultado después.
    Solo administradores (el reporte expone ingresos).
    """

    permission_classes = [IsAdminUser]

    def post(self, request):
        entrada = ReporteVentasInputSerializer(data=request.data)
        entrada.is_valid(raise_exception=True)
        _, respuesta = _encolar(generar_reporte_ventas, entrada.validated_data["evento_id"])
        return respuesta


class EnviarNotificacionView(APIView):
    """POST /api/v1/notificaciones/ -> encola una notificación masiva (solo admin)."""

    permission_classes = [IsAdminUser]

    def post(self, request):
        entrada = NotificacionMasivaInputSerializer(data=request.data)
        entrada.is_valid(raise_exception=True)
        mensaje = entrada.validated_data["mensaje"].strip()
        if not mensaje:
            return Response(
                {"error": "El mensaje es obligatorio.", "codigo": "validacion", "tipo": "bad_request"},
                status=status.HTTP_400_BAD_REQUEST,
            )
        _, respuesta = _encolar(
            enviar_notificacion_masiva, mensaje, entrada.validated_data["destinatarios"]
        )
        return respuesta


class EstadoTareaView(APIView):
    """GET /api/v1/tareas/<task_id>/ -> estado y resultado de una tarea async (solo admin)."""

    permission_classes = [IsAdminUser]

    def get(self, request, task_id):
        resultado = AsyncResult(task_id)
        cuerpo = {
            "task_id": task_id,
            "estado": resultado.status,  # PENDING / STARTED / SUCCESS / FAILURE
            "listo": resultado.ready(),
        }
        if resultado.ready() and resultado.successful():
            cuerpo["resultado"] = resultado.result
        return Response(cuerpo, status=status.HTTP_200_OK)


class IntegracionProxyView(APIView):
    """GET /api/v1/integracion/<recurso>/ -> proxy al microservicio Flask.

    Permite que el frontend consuma la info del sistema, el clima (API de
    terceros vía Adapter) y el aliado desde el mismo origen. Es resiliente:
    si el microservicio no responde, devuelve 503 con un cuerpo claro en vez
    de una excepción.
    """

    RECURSOS = {
        "info": "/api/v2/integracion/info",
        "clima": "/api/v2/integracion/clima",
        "aliado": "/api/v2/integracion/aliado",
    }

    def get(self, request, recurso):
        ruta = self.RECURSOS.get(recurso)
        if ruta is None:
            return Response(
                {"error": "Recurso de integración desconocido.", "tipo": "not_found"},
                status=status.HTTP_404_NOT_FOUND,
            )

        url = settings.INTEGRACION_SERVICE_URL.rstrip("/") + ruta
        try:
            resp = requests.get(url, params=request.query_params, timeout=6)
            return Response(resp.json(), status=resp.status_code)
        except requests.exceptions.RequestException as exc:
            return Response(
                {
                    "error": "El microservicio de integración no está disponible.",
                    "tipo": "service_unavailable",
                    "detalle": str(exc),
                },
                status=status.HTTP_503_SERVICE_UNAVAILABLE,
            )
