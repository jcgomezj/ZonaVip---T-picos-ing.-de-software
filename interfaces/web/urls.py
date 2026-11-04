from django.contrib.auth import views as auth_views
from django.urls import path

from . import views

app_name = "web"

urlpatterns = [
    path("", views.home, name="home"),
    path("panel/", views.panel, name="panel"),
    path("perfil/", views.perfil, name="perfil"),
    path("organizador/", views.organizador, name="organizador"),
    path("organizador/eventos/<int:evento_id>/cancelar/", views.organizador_cancelar_evento,
         name="organizador-cancelar-evento"),
    path("checkin/", views.checkin, name="checkin"),
    path("boletas/<str:codigo>/qr.png", views.qr_boleta, name="qr-boleta"),
    # Autenticación del frontend.
    path("login/", views.ZonaVipLoginView.as_view(), name="login"),
    path("registro/", views.registro, name="registro"),
    path(
        "logout/",
        auth_views.LogoutView.as_view(next_page="web:home"),
        name="logout",
    ),
]
