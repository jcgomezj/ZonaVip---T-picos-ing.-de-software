"""
Vistas del frontend de ZonaVip (Entrega 2).

Renderizan plantillas HTML modernas (Tailwind + Alpine.js) con soporte i18n
completo. La lógica de negocio sigue viviendo en el Service Layer / la API;
estas vistas solo consultan datos para pintarlos.
"""

from __future__ import annotations

from django.contrib.auth.decorators import login_required
from django.shortcuts import render
from django.utils.translation import gettext as _

from apps.eventos.models import Evento


def home(request):
    """Landing moderna con el catálogo de eventos publicados."""
    eventos = (
        Evento.objects.filter(estado=Evento.Estado.PUBLICADO)
        .select_related("organizador", "categoria")
        .prefetch_related("localidades")
    )
    contexto = {
        "eventos": eventos,
        "titulo_pagina": _("Eventos en vivo"),
    }
    return render(request, "web/home.html", contexto)


@login_required
def panel(request):
    """Panel de operaciones: integración (clima/aliado/info) y tareas async.

    ZONA PRIVADA: solo usuarios autenticados. `@login_required` redirige a la
    pantalla de login (`LOGIN_URL`) si no hay sesión. Es la vitrina de los
    requisitos de la Entrega 2: consume el microservicio de integración y
    dispara tareas de Celery, todo desde una UI moderna.
    """
    return render(request, "web/panel.html", {"titulo_pagina": _("Panel del sistema")})
