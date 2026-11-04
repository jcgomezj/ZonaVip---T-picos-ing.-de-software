"""Correo de aviso cuando un evento es cancelado (lo envía una tarea Celery)."""

from __future__ import annotations

import logging
from decimal import Decimal
from html import escape

from django.conf import settings
from django.core.mail import EmailMultiAlternatives
from django.utils import timezone

logger = logging.getLogger(__name__)


def _fmt(valor) -> str:
    return f"${Decimal(valor):,.0f}".replace(",", ".")


def construir_correo_cancelacion(usuario, evento, boletas, motivo: str = ""):
    nombre = usuario.get_full_name() or usuario.username
    fecha = timezone.localtime(evento.fecha_evento).strftime("%d/%m/%Y %H:%M")
    reembolso = sum((Decimal(b.precio) for b in boletas if b.pago_id), Decimal(0))
    motivo = motivo.strip()
    texto = [f"Hola {nombre},", "",
             f"Lamentamos informarte que el evento «{evento.titulo}» ({fecha}, {evento.lugar}) fue cancelado."]
    if motivo:
        texto += ["", f"Motivo: {motivo}"]
    texto += ["", f"Tus {len(boletas)} boleta(s) fueron canceladas."]
    if reembolso > 0:
        texto.append(f"Reembolso total: {_fmt(reembolso)} al mismo medio de pago.")
    texto += ["", "Gracias por tu comprensión. — Zona VIP"]

    extra_motivo = f'<p style="color:#a1a1aa;">Motivo: {escape(motivo)}</p>' if motivo else ""
    extra_reemb = f'<p style="color:#fff;font-weight:700;">Reembolso: {_fmt(reembolso)}</p>' if reembolso > 0 else ""
    html = f"""
    <div style="background:#09090b;padding:24px;font-family:Arial,Helvetica,sans-serif;color:#d4d4d8;">
      <div style="max-width:560px;margin:auto;background:#111114;border:1px solid #27272a;border-radius:16px;overflow:hidden;">
        <div style="padding:24px;background:linear-gradient(135deg,#7f1d1d,#be123c);color:#fff;">
          <div style="font-size:12px;letter-spacing:.2em;">ZONA VIP</div>
          <h1 style="margin:8px 0 0;font-size:22px;">Evento cancelado</h1>
        </div>
        <div style="padding:24px;">
          <p>Hola {escape(nombre)}, el evento <strong style="color:#fff;">{escape(evento.titulo)}</strong>
             ({fecha} · {escape(evento.lugar)}) fue cancelado.</p>
          {extra_motivo}
          <p>Tus <strong style="color:#fff;">{len(boletas)}</strong> boleta(s) fueron canceladas.</p>
          {extra_reemb}
        </div>
      </div>
    </div>"""
    correo = EmailMultiAlternatives(
        subject=f"Evento cancelado: {evento.titulo} · Zona VIP", body="\n".join(texto),
        from_email=getattr(settings, "DEFAULT_FROM_EMAIL", None), to=[usuario.email],
    )
    correo.attach_alternative(html, "text/html")
    return correo


def enviar_correo_cancelacion_evento(usuario, evento, boletas, motivo: str = "") -> bool:
    """Best-effort: nunca lanza; True si se entregó al backend."""
    try:
        return bool(construir_correo_cancelacion(usuario, evento, boletas, motivo).send())
    except Exception:  # noqa: BLE001
        logger.exception("No se pudo enviar el aviso de cancelación al usuario %s", usuario.pk)
        return False
