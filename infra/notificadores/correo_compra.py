"""
Correo de confirmación de compra (resumen de pago + un QR por boleta).

Se envía con el backend de correo de Django configurado en `EMAIL_BACKEND`:
  - por defecto `console` (el correo completo se imprime en la terminal del
    servidor, ideal para desarrollo / demo);
  - con las variables `EMAIL_HOST`, `EMAIL_HOST_USER`, ... se usa SMTP real.

Los QR viajan incrustados (Content-ID) para que se vean sin descargar nada.
"""

from __future__ import annotations

import logging
from decimal import Decimal
from email.mime.image import MIMEImage
from html import escape

from django.conf import settings
from django.core.mail import EmailMultiAlternatives
from django.utils import timezone

from infra.qr import png_qr_estatico

logger = logging.getLogger(__name__)


def _fmt(valor: Decimal | float | int) -> str:
    return f"${Decimal(valor):,.0f}".replace(",", ".")


def construir_correo(usuario, boletas) -> EmailMultiAlternatives:
    primera = boletas[0]
    evento = primera.evento
    total = sum((Decimal(b.precio) for b in boletas), Decimal(0))
    fecha = timezone.localtime(evento.fecha_evento).strftime("%d/%m/%Y %H:%M")
    nombre = usuario.get_full_name() or usuario.username
    asunto = f"Tus entradas para {evento.titulo} · Zona VIP"

    texto = [
        f"Hola {nombre},",
        "",
        "¡Tu compra fue exitosa! Estos son los detalles:",
        f"Evento: {evento.titulo}",
        f"Lugar: {evento.lugar}",
        f"Fecha: {fecha}",
        "",
    ]
    filas_html = []
    for i, b in enumerate(boletas, start=1):
        texto.append(f"  {i}. {b.localidad.nombre} — {_fmt(b.precio)} — código {b.codigo_qr}")
        filas_html.append(
            f"""
            <tr>
              <td style="padding:16px;border-bottom:1px solid #27272a;">
                <div style="font-weight:600;color:#fff;">Boleta {i} · {escape(b.localidad.nombre)}</div>
                <div style="font-size:12px;color:#a1a1aa;margin:4px 0 0;">Código: {b.codigo_qr}</div>
                <div style="color:#c4b5fd;margin-top:4px;">{_fmt(b.precio)}</div>
              </td>
              <td style="padding:16px;border-bottom:1px solid #27272a;text-align:right;">
                <img src="cid:qr{i}" width="120" height="120" alt="QR boleta {i}"
                     style="background:#fff;padding:6px;border-radius:8px;">
              </td>
            </tr>"""
        )
    texto += [
        "",
        f"Cantidad: {len(boletas)}",
        f"Total pagado: {_fmt(total)}",
        "",
        "Presenta el código QR de cada boleta en el ingreso. También puedes "
        "verlos en tu perfil de Zona VIP.",
    ]

    html = f"""
    <div style="background:#09090b;padding:24px;font-family:Arial,Helvetica,sans-serif;color:#d4d4d8;">
      <div style="max-width:560px;margin:auto;background:#111114;border:1px solid #27272a;border-radius:16px;overflow:hidden;">
        <div style="padding:24px;background:linear-gradient(135deg,#4c1d95,#a21caf);color:#fff;">
          <div style="font-size:12px;letter-spacing:.2em;">ZONA VIP</div>
          <h1 style="margin:8px 0 0;font-size:22px;">¡Compra confirmada!</h1>
        </div>
        <div style="padding:24px;">
          <p>Hola {escape(nombre)}, aquí tienes tus entradas para
             <strong style="color:#fff;">{escape(evento.titulo)}</strong>.</p>
          <p style="font-size:13px;color:#a1a1aa;">{escape(evento.lugar)} · {fecha}</p>
          <table width="100%" cellspacing="0" cellpadding="0" style="margin-top:16px;">{''.join(filas_html)}</table>
          <table width="100%" style="margin-top:16px;">
            <tr><td>Boletas</td><td style="text-align:right;">{len(boletas)}</td></tr>
            <tr><td style="color:#fff;font-weight:700;">Total pagado</td>
                <td style="text-align:right;color:#fff;font-weight:700;">{_fmt(total)}</td></tr>
          </table>
          <p style="font-size:12px;color:#71717a;margin-top:24px;">
            Presenta el QR de cada boleta en el ingreso. ¿Dudas? Escríbenos desde el chat de soporte 24/7.</p>
        </div>
      </div>
    </div>"""

    correo = EmailMultiAlternatives(
        subject=asunto,
        body="\n".join(texto),
        from_email=getattr(settings, "DEFAULT_FROM_EMAIL", None),
        to=[usuario.email],
    )
    correo.attach_alternative(html, "text/html")
    correo.mixed_subtype = "related"
    for i, b in enumerate(boletas, start=1):
        img = MIMEImage(png_qr_estatico(b.codigo_qr), _subtype="png")
        img.add_header("Content-ID", f"<qr{i}>")
        img.add_header("Content-Disposition", "inline", filename=f"qr-{i}.png")
        correo.attach(img)
    return correo


def enviar_correo_compra(usuario, boletas) -> bool:
    """Envía el correo de la compra. Nunca lanza: un fallo de correo no debe
    deshacer una compra ya pagada. Devuelve True si se entregó al backend."""
    if not boletas:
        return False
    if not usuario.email:
        logger.warning("Usuario %s sin email: no se envía confirmación.", usuario.pk)
        return False
    try:
        return bool(construir_correo(usuario, list(boletas)).send(fail_silently=False))
    except Exception:  # noqa: BLE001 - el correo es best-effort
        logger.exception("No se pudo enviar el correo de compra")
        return False
