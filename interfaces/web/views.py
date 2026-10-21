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

import datetime
from decimal import Decimal

from django.contrib import messages
from django.contrib.auth import get_user_model, login
from django.contrib.auth.decorators import login_required, user_passes_test
from django.contrib.auth.views import LoginView
from django.db.models import Count, Q, Sum
from django.http import Http404, HttpResponse
from django.shortcuts import redirect, render
from django.urls import reverse
from django.utils import timezone
from django.utils.http import url_has_allowed_host_and_scheme
from django.utils.translation import gettext as _
from django.views.decorators.cache import never_cache

from apps.boletas.models import Boleta
from apps.eventos.models import CategoriaEvento, Evento
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


def _boletas_vencidas_simuladas() -> list[dict]:
    """Historial simulado: exactamente DOS boletas de un evento pasado."""
    fecha = timezone.now() - datetime.timedelta(days=45)
    return [
        {
            "evento": "Noche Eléctrica 2025",
            "lugar": "Plaza Mayor, Medellín",
            "fecha": fecha,
            "localidad": "General",
            "codigo": "ZV-EXP-" + suf,
            "precio": Decimal("140000"),
        }
        for suf in ("A1F4C9", "A1F4CA")
    ]


@login_required
def perfil(request):
    """Perfil del usuario: SOLO boletas recientes (QR dinámico) y 2 vencidas."""
    ahora = timezone.now()
    recientes = (
        Boleta.objects.filter(
            usuario=request.user,
            estado__in=[Boleta.Estado.PAGADA, Boleta.Estado.RESERVADA],
            evento__fecha_evento__gte=ahora,
        )
        .select_related("evento", "localidad")
        .order_by("-creado_en")[:12]
    )
    return render(
        request,
        "web/perfil.html",
        {
            "boletas": recientes,
            "vencidas": _boletas_vencidas_simuladas(),
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
    ventas = Boleta.objects.exclude(estado=Boleta.Estado.CANCELADA).aggregate(
        boletas=Count("id"), ingresos=Sum("precio")
    )
    por_evento = list(
        Boleta.objects.exclude(estado=Boleta.Estado.CANCELADA)
        .values("evento__titulo")
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
