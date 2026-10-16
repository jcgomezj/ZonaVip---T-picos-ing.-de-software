"""
Tareas asíncronas de ZonaVip (Celery + Redis) — Entrega 2.

Procesos de fondo que NO deben bloquear el ciclo request/response de Django:

  - generar_reporte_ventas: agrega las ventas por evento/localidad. En un
    monolito síncrono, un reporte pesado bloquea el worker WSGI y causa
    *timeouts*; encolándolo en Celery, la petición responde de inmediato y el
    reporte se calcula en segundo plano.

  - enviar_notificacion_masiva: simula el envío de notificaciones a muchos
    usuarios (correo/push), un proceso naturalmente asíncrono.

Las tareas se definen con @shared_task para no acoplarlas a la instancia
concreta de Celery (buena práctica en apps Django reutilizables).
"""

from __future__ import annotations

import time

from celery import shared_task


@shared_task(bind=True, name="reportes.generar_reporte_ventas")
def generar_reporte_ventas(self, evento_id: int | None = None) -> dict:
    """Agrega las ventas (boletas) por localidad. Devuelve un resumen.

    Se ejecuta en el worker de Celery, no en el proceso web.
    """
    # Import diferido: evita cargar el ORM al importar el módulo de tasks
    # (y rompe un posible import circular con la app de boletas).
    from apps.boletas.models import Boleta

    qs = Boleta.objects.all()
    if evento_id is not None:
        qs = qs.filter(evento_id=evento_id)

    total_boletas = qs.count()
    total_ingresos = float(sum(b.precio for b in qs))
    por_estado: dict[str, int] = {}
    for boleta in qs:
        por_estado[boleta.estado] = por_estado.get(boleta.estado, 0) + 1

    return {
        "evento_id": evento_id,
        "total_boletas": total_boletas,
        "total_ingresos": total_ingresos,
        "por_estado": por_estado,
        "generado_por": "celery-worker",
    }


@shared_task(name="reportes.enviar_notificacion_masiva")
def enviar_notificacion_masiva(mensaje: str, destinatarios: int = 100) -> dict:
    """Simula el envío asíncrono de una notificación a muchos usuarios."""
    # Simula trabajo de I/O (envío de correos/push) sin bloquear la web.
    time.sleep(1)
    return {
        "mensaje": mensaje,
        "destinatarios_notificados": destinatarios,
        "estado": "completado",
    }
