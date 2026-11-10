"""
Consultas de solo lectura: panel del organizador.

Agregaciones en BD con número CONSTANTE de consultas (no crece con boletas):
eventos(+organizador), localidades (prefetch), boletas agrupadas COUNT/SUM.
"""

from __future__ import annotations

from decimal import Decimal
from typing import Optional

from django.db.models import Count, Sum

from apps.boletas.models import Boleta
from apps.eventos.models import Evento

_INGRESO = (Boleta.Estado.PAGADA, Boleta.Estado.USADA)
_CLAVE = {
    Boleta.Estado.RESERVADA: "reservadas", Boleta.Estado.PAGADA: "pagadas",
    Boleta.Estado.USADA: "usadas", Boleta.Estado.CANCELADA: "canceladas",
}


def _pct(parte: int, total: int) -> int:
    return 0 if total <= 0 else min(100, round(parte * 100 / total))


def _vacio() -> dict:
    return {"reservadas": 0, "pagadas": 0, "usadas": 0, "canceladas": 0, "ingresos": Decimal(0)}


def resumen_organizador(organizador_id: Optional[int] = None) -> dict:
    """Ventas por localidad y ocupación. `None` = todos (administrador)."""
    eventos = (
        Evento.objects.select_related("organizador", "categoria")
        .prefetch_related("localidades").order_by("fecha_evento")
    )
    if organizador_id is not None:
        eventos = eventos.filter(organizador_id=organizador_id)
    eventos = list(eventos)

    filas = (
        Boleta.objects.filter(evento__in=[e.id for e in eventos])
        .values("localidad_id", "estado").annotate(n=Count("id"), total=Sum("precio"))
    )
    por_loc: dict[int, dict] = {}
    for f in filas:
        d = por_loc.setdefault(f["localidad_id"], _vacio())
        d[_CLAVE[f["estado"]]] += f["n"]
        if f["estado"] in _INGRESO:
            d["ingresos"] += f["total"] or Decimal(0)

    totales = {"eventos": len(eventos), "eventos_activos": 0, "pagadas": 0, "reservadas": 0,
               "usadas": 0, "canceladas": 0, "ingresos": Decimal(0), "cupo": 0, "vendidas": 0}
    salida = []
    for e in eventos:
        locs = []
        ev = {**_vacio(), "cupo": 0, "vendidas": 0}
        for loc in e.localidades.all():
            d = por_loc.get(loc.id, _vacio())
            locs.append({
                "id": loc.id, "nombre": loc.nombre, "tipo": loc.tipo, "precio": float(loc.precio),
                "cupo": loc.cupo, "vendidas": loc.vendidas,
                "disponibles": max(loc.cupo - loc.vendidas, 0),
                "ocupacion_pct": _pct(loc.vendidas, loc.cupo),
                "reservadas": d["reservadas"], "pagadas": d["pagadas"],
                "usadas": d["usadas"], "canceladas": d["canceladas"],
                "ingresos": float(d["ingresos"]),
                "asistencia_pct": _pct(d["usadas"], d["pagadas"] + d["usadas"]),
            })
            for k in ("reservadas", "pagadas", "usadas", "canceladas", "ingresos"):
                ev[k] += d[k]
            ev["cupo"] += loc.cupo
            ev["vendidas"] += loc.vendidas
        salida.append({
            "id": e.id, "titulo": e.titulo, "lugar": e.lugar, "estado": e.estado,
            "fecha_evento": e.fecha_evento, "organizador": e.organizador.nombre_empresarial,
            "cancelable": e.estado in (Evento.Estado.BORRADOR, Evento.Estado.PUBLICADO),
            "ocupacion_pct": _pct(ev["vendidas"], ev["cupo"]),
            "asistencia_pct": _pct(ev["usadas"], ev["pagadas"] + ev["usadas"]),
            **{k: (float(v) if isinstance(v, Decimal) else v) for k, v in ev.items()},
            "localidades": locs,
        })
        if e.estado == Evento.Estado.PUBLICADO:
            totales["eventos_activos"] += 1
        if e.estado != Evento.Estado.CANCELADO:
            for k in ("pagadas", "reservadas", "usadas", "ingresos", "cupo", "vendidas"):
                totales[k] += ev[k]
        totales["canceladas"] += ev["canceladas"]

    totales["ocupacion_pct"] = _pct(totales["vendidas"], totales["cupo"])
    totales["ingresos"] = float(totales["ingresos"])
    return {"totales": totales, "eventos": salida}


def evento_del_organizador(evento_id: int, organizador_id: Optional[int]) -> Optional[Evento]:
    """El evento si el organizador puede verlo (`None` = admin: cualquiera)."""
    eventos = Evento.objects.filter(id=evento_id)
    if organizador_id is not None:
        eventos = eventos.filter(organizador_id=organizador_id)
    return eventos.first()


def asistentes_evento(evento: Evento):
    """Boletas cobradas (PAGADA o USADA) de un evento, listas para exportar.

    Una sola consulta (JOIN con usuario, localidad y validador), ordenada por
    localidad y comprador para que la lista sea fácil de usar en la puerta."""
    return (
        Boleta.objects.filter(evento=evento, estado__in=_INGRESO)
        .select_related("usuario", "localidad", "validada_por")
        .order_by("localidad__nombre", "usuario__username", "id")
    )
