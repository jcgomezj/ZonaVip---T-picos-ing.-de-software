from django.urls import path

from . import views

app_name = "api"

urlpatterns = [
    path("eventos/", views.EventoListCreateView.as_view(), name="evento-list-create"),
    path(
        "eventos/<int:evento_id>/publicar/",
        views.EventoPublicarView.as_view(),
        name="evento-publicar",
    ),
    path("boletas/reservar/", views.ReservarBoletaView.as_view(), name="boleta-reservar"),
    path(
        "boletas/<int:boleta_id>/cancelar/",
        views.CancelarBoletaView.as_view(),
        name="boleta-cancelar",
    ),
    path("boletas/mias/", views.MisBoletasView.as_view(), name="boleta-mias"),
]
