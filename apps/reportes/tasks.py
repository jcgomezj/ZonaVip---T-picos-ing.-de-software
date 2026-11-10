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

import logging
import time

from celery import shared_task

logger = logging.getLogger(__name__)


@shared_task(bind=True, name="reportes.generar_reporte_ventas")
def generar_reporte_ventas(self, evento_id: int | None = None) -> dict:
    """Agrega las ventas (boletas) por localidad. Devuelve un resumen.

    Optimizado para PostgreSQL: ejecuta agregaciones a nivel de base de datos
    (Sum y Count con GROUP BY) evitando cargar miles de registros en la memoria de Python
    y aprovechando los índices compuestos en (evento, estado).
    """
    from django.db.models import Count, Sum
    from apps.boletas.models import Boleta

    qs = Boleta.objects.all()
    if evento_id is not None:
        qs = qs.filter(evento_id=evento_id)

    total_boletas = qs.count()
    # Ingreso real: solo boletas cobradas (pagadas o usadas).
    agregados = qs.filter(estado__in=[Boleta.Estado.PAGADA, Boleta.Estado.USADA]).aggregate(
        total_ingresos=Sum("precio")
    )
    total_ingresos = float(agregados["total_ingresos"] or 0.0)

    # Conteo agrupado por estado directamente en la base de datos
    estados_agg = qs.values("estado").annotate(cantidad=Count("id"))
    por_estado = {item["estado"]: item["cantidad"] for item in estados_agg}

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


@shared_task(name="reportes.expirar_reservas_vencidas")
def expirar_reservas_vencidas() -> dict:
    """Periódica (Celery beat, cada minuto): cancela reservas sin pagar
    vencidas y devuelve el cupo."""
    from application.services import ExpirarReservasService

    return {"reservas_expiradas": ExpirarReservasService().ejecutar()}


@shared_task(name="reportes.notificar_cancelacion_evento", ignore_result=True)
def notificar_cancelacion_evento(evento_id: int, motivo: str = "") -> dict:
    """Avisa por correo, en segundo plano, a cada usuario con boletas afectadas
    por la cancelación de un evento (un correo por usuario)."""
    from collections import defaultdict

    from apps.boletas.models import Boleta
    from apps.eventos.models import Evento
    from infra.notificadores.correo_evento import enviar_correo_cancelacion_evento

    evento = Evento.objects.get(id=evento_id)
    boletas = (
        Boleta.objects.filter(
            evento=evento, estado=Boleta.Estado.CANCELADA,
            motivo_cancelacion=Boleta.MotivoCancelacion.EVENTO_CANCELADO,
        ).select_related("usuario", "localidad", "pago").order_by("id")
    )
    por_usuario = defaultdict(list)
    for b in boletas:
        por_usuario[b.usuario_id].append(b)

    enviados = sin_email = 0
    for lista in por_usuario.values():
        usuario = lista[0].usuario
        if not usuario.email:
            sin_email += 1
            continue
        if enviar_correo_cancelacion_evento(usuario, evento, lista, motivo):
            enviados += 1
    resultado = {"evento_id": evento_id, "usuarios_afectados": len(por_usuario),
                 "correos_enviados": enviados, "sin_email": sin_email}
    logger.info("Notificación de cancelación de evento: %s", resultado)
    return resultado
