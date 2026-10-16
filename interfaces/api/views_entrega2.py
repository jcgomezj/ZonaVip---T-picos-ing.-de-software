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

import requests
from celery.result import AsyncResult
from django.conf import settings
from rest_framework import status
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.reportes.tasks import (
    enviar_notificacion_masiva,
    generar_reporte_ventas,
)


class GenerarReporteView(APIView):
    """POST /api/v1/reportes/ventas/ -> encola el reporte en Celery (asíncrono).

    Devuelve 202 Accepted + un task_id para consultar el resultado después.
    """

    def post(self, request):
        evento_id = request.data.get("evento_id")
        tarea = generar_reporte_ventas.delay(evento_id)
        return Response(
            {
                "task_id": tarea.id,
                "estado": "encolado",
                "consultar_en": f"/api/v1/tareas/{tarea.id}/",
            },
            status=status.HTTP_202_ACCEPTED,
        )


class EnviarNotificacionView(APIView):
    """POST /api/v1/notificaciones/ -> encola una notificación masiva."""

    def post(self, request):
        mensaje = request.data.get("mensaje", "")
        if not mensaje.strip():
            return Response(
                {"error": "El mensaje es obligatorio.", "tipo": "bad_request"},
                status=status.HTTP_400_BAD_REQUEST,
            )
        destinatarios = int(request.data.get("destinatarios", 100))
        tarea = enviar_notificacion_masiva.delay(mensaje, destinatarios)
        return Response(
            {
                "task_id": tarea.id,
                "estado": "encolado",
                "consultar_en": f"/api/v1/tareas/{tarea.id}/",
            },
            status=status.HTTP_202_ACCEPTED,
        )


class EstadoTareaView(APIView):
    """GET /api/v1/tareas/<task_id>/ -> estado y resultado de una tarea async."""

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
