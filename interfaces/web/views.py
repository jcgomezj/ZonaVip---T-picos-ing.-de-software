"""
Vistas del frontend de ZonaVip.

Renderizan plantillas HTML (Tailwind + Alpine.js) con soporte i18n. La lógica
de negocio vive en el Service Layer / la API; estas vistas solo consultan datos
para pintarlos y aplican control de acceso:

  - Compra: exige sesión (la API la rechaza con 403 y el front redirige a
    registro/login).
  - Panel del sistema: exclusivo del rol administrador (`is_staff`).
  - Perfil: solo para usuarios autenticados.
"""

from __future__ import annotations

import csv
import datetime

from django.contrib import messages
from django.contrib.auth import get_user_model, login
from django.contrib.auth.decorators import login_required
from django.contrib.auth.views import LoginView
from django.db.models import Count, Q, Sum
from django.http import Http404, HttpResponse
from django.shortcuts import redirect, render
from django.urls import reverse
from django.utils import timezone
from django.utils.http import url_has_allowed_host_and_scheme
from django.utils.translation import gettext as _
from django.views.decorators.cache import never_cache
from django.views.decorators.http import require_POST

from apps.boletas.models import Boleta
from apps.eventos.models import CategoriaEvento, Evento, Organizador
from application.queries import asistentes_evento, evento_del_organizador, resumen_organizador
from application.services import CancelarEventoDTO, CancelarEventoService
from domain.exceptions import DomainError
from infra.qr import png_qr_dinamico

from .forms import RegistroForm
from .presenters import EventoCardVM

Usuario = get_user_model()


def es_admin(user) -> bool:
    """Rol administrador = staff activo. Único rol con acceso al panel."""
    return bool(user.is_authenticated and user.is_active and user.is_staff)


def _destino_seguro(request, valor: str, defecto: str) -> str:
    if valor and url_has_allowed_host_and_scheme(
        valor, allowed_hosts={request.get_host()}, require_https=request.is_secure()
    ):
        return valor
    return defecto


def home(request):
    """Landing con la cartelera de eventos publicados.

    Queries totales (constantes, sin importar cuántos eventos haya):
      1) eventos + organizador + categoría (JOIN)
      2) localidades de esos eventos (prefetch)
      3) categorías con conteo de eventos publicados (filtros)
    """
    eventos = (
        Evento.objects.filter(estado=Evento.Estado.PUBLICADO)
        .select_related("organizador", "categoria")
        .prefetch_related("localidades")
    )

    categoria_activa = None
    categoria_param = request.GET.get("categoria", "")
    if categoria_param.isdigit():
        categoria_activa = int(categoria_param)
        eventos = eventos.filter(categoria_id=categoria_activa)

    q = request.GET.get("q", "").strip()
    if q:
        eventos = eventos.filter(titulo__icontains=q)

    cards = [EventoCardVM(e) for e in eventos]

    categorias = (
        CategoriaEvento.objects.annotate(
            total=Count("eventos", filter=Q(eventos__estado=Evento.Estado.PUBLICADO))
        )
        .filter(total__gt=0)
        .order_by("nombre")
    )

    comprar = request.GET.get("comprar", "")
    contexto = {
        "cards": cards,
        "destacado": cards[0] if cards else None,
        "categorias": categorias,
        "categoria_activa": categoria_activa,
        "q": q,
        "hay_filtros": bool(q or categoria_activa),
        "checkout_payload": [c.como_json() for c in cards],
        # Tras registrarse/loguearse el usuario vuelve con ?comprar=<id> y el
        # checkout se reabre solo.
        "comprar_id": int(comprar) if comprar.isdigit() else None,
        "titulo_pagina": _("Eventos en vivo"),
    }
    return render(request, "web/home.html", contexto)


# ---------------------------------------------------------------------------
# Autenticación
# ---------------------------------------------------------------------------


class ZonaVipLoginView(LoginView):
    template_name = "web/login.html"
    redirect_authenticated_user = True

    def get_default_redirect_url(self):
        # El admin aterriza en su panel; el resto, en la cartelera.
        return reverse("web:panel") if es_admin(self.request.user) else reverse("web:home")


def registro(request):
    """Alta de cuenta. Inicia sesión automáticamente y respeta `?next=`."""
    siguiente = _destino_seguro(
        request, request.POST.get("next") or request.GET.get("next", ""), reverse("web:home")
    )
    if request.user.is_authenticated:
        return redirect(siguiente)

    form = RegistroForm(request.POST or None)
    if request.method == "POST" and form.is_valid():
        usuario = form.save()
        login(request, usuario, backend="django.contrib.auth.backends.ModelBackend")
        messages.success(request, _("¡Cuenta creada! Ya puedes comprar tus entradas."))
        return redirect(siguiente)
    return render(request, "web/registro.html", {"form": form, "next": siguiente})


# ---------------------------------------------------------------------------
# Perfil del usuario
# ---------------------------------------------------------------------------


@login_required
def perfil(request):
    """Perfil con datos reales:
      - `boletas`: pagadas de eventos futuros (QR dinámico).
      - `pendientes`: reservas sin pagar aún vigentes (se pueden pagar).
      - `historial`: lo demás (pasadas, usadas, canceladas, reservas vencidas).
    """
    ahora = timezone.now()
    base = Boleta.objects.filter(usuario=request.user).select_related("evento", "localidad")
    activa = Q(estado=Boleta.Estado.PAGADA, evento__fecha_evento__gte=ahora)
    pendiente = Q(estado=Boleta.Estado.RESERVADA, evento__fecha_evento__gte=ahora) & (
        Q(expira_en__isnull=True) | Q(expira_en__gt=ahora)
    )
    return render(
        request,
        "web/perfil.html",
        {
            "boletas": base.filter(activa).order_by("-creado_en")[:12],
            "pendientes": base.filter(pendiente).order_by("expira_en"),
            "historial": base.exclude(activa | pendiente).order_by("-evento__fecha_evento", "-id")[:30],
            "titulo_pagina": _("Mi perfil"),
        },
    )


@login_required
@never_cache
def qr_boleta(request, codigo: str):
    """PNG del QR dinámico de una boleta (solo su dueño)."""
    if not Boleta.objects.filter(codigo_qr=codigo, usuario=request.user).exists():
        raise Http404
    respuesta = HttpResponse(png_qr_dinamico(codigo), content_type="image/png")
    respuesta["Cache-Control"] = "no-store"
    return respuesta


# ---------------------------------------------------------------------------
# Panel del sistema (solo administrador)
# ---------------------------------------------------------------------------


def _solo_admin(vista):
    """Anónimo -> login; autenticado sin rol admin -> 404 (la ruta 'no existe')."""

    def envoltura(request, *args, **kwargs):
        if not request.user.is_authenticated:
            return redirect(f"{reverse('web:login')}?next={request.path}")
        if not es_admin(request.user):
            raise Http404
        return vista(request, *args, **kwargs)

    envoltura.__name__ = vista.__name__
    return envoltura


@_solo_admin
def panel(request):
    """Panel de operaciones (admin): clima de sede, aliados e informes de ventas."""
    cobradas = Boleta.objects.filter(estado__in=[Boleta.Estado.PAGADA, Boleta.Estado.USADA])
    ventas = cobradas.aggregate(boletas=Count("id"), ingresos=Sum("precio"))
    por_evento = list(
        cobradas.values("evento__titulo")
        .annotate(boletas=Count("id"), ingresos=Sum("precio"))
        .order_by("-ingresos")[:5]
    )
    resumen = {
        "boletas": ventas["boletas"] or 0,
        "ingresos": float(ventas["ingresos"] or 0),
        "eventos_activos": Evento.objects.filter(estado=Evento.Estado.PUBLICADO).count(),
        "top": [
            {
                "evento": f["evento__titulo"],
                "boletas": f["boletas"],
                "ingresos": float(f["ingresos"] or 0),
            }
            for f in por_evento
        ],
    }
    return render(
        request,
        "web/panel.html",
        {"titulo_pagina": _("Panel del sistema"), "resumen_ventas": resumen},
    )


# ---------------------------------------------------------------------------
# Organizador y check-in
# ---------------------------------------------------------------------------


def _organizador_de(user):
    return Organizador.objects.filter(usuario_id=user.pk).first()


def _es_organizador_o_admin(user) -> bool:
    return bool(user.is_active and (user.is_staff or _organizador_de(user)))


def _solo_organizador_o_admin(vista):
    """Anónimo -> login; sin el rol -> 404 (la ruta 'no existe')."""

    def envoltura(request, *args, **kwargs):
        if not request.user.is_authenticated:
            return redirect(f"{reverse('web:login')}?next={request.path}")
        if not _es_organizador_o_admin(request.user):
            raise Http404
        return vista(request, *args, **kwargs)

    envoltura.__name__ = vista.__name__
    return envoltura


@_solo_organizador_o_admin
def organizador(request):
    """Panel del organizador: ventas por localidad, ocupación y asistencia.
    Un organizador ve solo sus eventos; el admin ve todos."""
    perfil_org = _organizador_de(request.user)
    resumen = resumen_organizador(perfil_org.id if perfil_org else None)
    return render(request, "web/organizador.html",
                  {"resumen": resumen, "titulo_pagina": _("Panel del organizador")})


@_solo_organizador_o_admin
@require_POST
def organizador_cancelar_evento(request, evento_id: int):
    dto = CancelarEventoDTO(
        evento_id=evento_id, usuario_id=request.user.id, es_staff=request.user.is_staff,
        motivo=request.POST.get("motivo", "").strip()[:300],
    )
    try:
        r = CancelarEventoService().ejecutar(dto)
    except DomainError as error:
        messages.error(request, str(error))
    else:
        messages.success(
            request,
            _("Evento cancelado: %(n)s boleta(s) anuladas y reembolsadas. "
              "Los asistentes recibirán un correo.") % {"n": r.boletas_canceladas},
        )
    return redirect("web:organizador")


def _celda_csv(valor) -> str:
    """Evita la inyección de fórmulas al abrir el CSV en Excel/Sheets: un texto
    que empieza por = + - @ (p. ej. un nombre de usuario malicioso) se
    antepone con un apóstrofo para que se muestre como texto."""
    texto = "" if valor is None else str(valor)
    return "'" + texto if texto[:1] in ("=", "+", "-", "@", "\t", "\r") else texto


@_solo_organizador_o_admin
def organizador_asistentes_csv(request, evento_id: int):
    """Descarga la lista de asistentes (boletas PAGADAS/USADAS) en CSV.
    El organizador solo puede exportar sus eventos; el admin, cualquiera."""
    perfil_org = None if request.user.is_staff else _organizador_de(request.user)
    evento = evento_del_organizador(evento_id, perfil_org.id if perfil_org else None)
    if evento is None:
        raise Http404

    respuesta = HttpResponse(content_type="text/csv; charset=utf-8")
    nombre = f"asistentes-evento-{evento.id}-{timezone.localdate():%Y%m%d}.csv"
    respuesta["Content-Disposition"] = f'attachment; filename="{nombre}"'
    respuesta["Cache-Control"] = "no-store"
    respuesta.write("﻿")  # BOM: Excel abre bien tildes y eñes.

    escritor = csv.writer(respuesta)
    escritor.writerow([
        _("Código"), _("Asistente"), _("Usuario"), _("Correo"), _("Localidad"),
        _("Precio"), _("Estado"), _("Comprada"), _("Ingresó"), _("Validada por"),
    ])
    formato = "%Y-%m-%d %H:%M"
    for b in asistentes_evento(evento):
        escritor.writerow([_celda_csv(v) for v in (
            b.codigo_qr,
            b.usuario.get_full_name(),
            b.usuario.get_username(),
            b.usuario.email,
            b.localidad.nombre,
            f"{b.precio:.0f}",
            b.get_estado_display(),
            timezone.localtime(b.creado_en).strftime(formato),
            timezone.localtime(b.usada_en).strftime(formato) if b.usada_en else "",
            b.validada_por.get_username() if b.validada_por else "",
        )])
    return respuesta


@_solo_organizador_o_admin
def checkin(request):
    """Control de acceso: escanea o digita el QR. La validación real ocurre en
    la API (`POST /api/v1/boletas/validar/`)."""
    eventos = Evento.objects.filter(
        estado=Evento.Estado.PUBLICADO,
        fecha_evento__gte=timezone.now() - datetime.timedelta(days=2),
    ).order_by("fecha_evento")
    perfil_org = _organizador_de(request.user)
    if not request.user.is_staff and perfil_org:
        eventos = eventos.filter(organizador=perfil_org)
    return render(request, "web/checkin.html",
                  {"eventos": eventos[:50], "titulo_pagina": _("Control de acceso")})
