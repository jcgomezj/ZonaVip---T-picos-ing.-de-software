from django.urls import path

from . import views, views_entrega2 as v2

app_name = "api"

urlpatterns = [
    # --- Entrega 1: catálogo y boletas ---
    path("eventos/", views.EventoListCreateView.as_view(), name="evento-list-create"),
    path(
        "eventos/<int:evento_id>/publicar/",
        views.EventoPublicarView.as_view(),
        name="evento-publicar",
    ),
    path("boletas/reservar/", views.ReservarBoletaView.as_view(), name="boleta-reservar"),
    path("boletas/comprar/", views.ComprarBoletasView.as_view(), name="boleta-comprar"),
    path(
        "boletas/<int:boleta_id>/cancelar/",
        views.CancelarBoletaView.as_view(),
        name="boleta-cancelar",
    ),
    path("boletas/mias/", views.MisBoletasView.as_view(), name="boleta-mias"),
    path("boletas/validar/", views.ValidarBoletaView.as_view(), name="boleta-validar"),
    path("boletas/<int:boleta_id>/pagar/", views.PagarReservaView.as_view(), name="boleta-pagar"),
    path("eventos/<int:evento_id>/cancelar/", views.EventoCancelarView.as_view(), name="evento-cancelar"),
    path("organizador/resumen/", views.OrganizadorResumenView.as_view(), name="organizador-resumen"),

    # --- Entrega 2: tareas asíncronas (Celery + Redis) ---
    path("reportes/ventas/", v2.GenerarReporteView.as_view(), name="reporte-ventas"),
    path("notificaciones/", v2.EnviarNotificacionView.as_view(), name="notificacion-masiva"),
    path("tareas/<str:task_id>/", v2.EstadoTareaView.as_view(), name="tarea-estado"),

    # --- Entrega 2: proxy al microservicio de integración ---
    path(
        "integracion/<str:recurso>/",
        v2.IntegracionProxyView.as_view(),
        name="integracion-proxy",
    ),
]
