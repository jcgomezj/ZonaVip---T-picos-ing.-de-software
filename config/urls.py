from django.contrib import admin
from django.urls import include, path

urlpatterns = [
    path("admin/", admin.site.urls),
    # Cambio de idioma (i18n): POST a /i18n/setlang/ guarda el idioma elegido
    # en la sesión/cookie. Lo usa el selector ES/EN del frontend.
    path("i18n/", include("django.conf.urls.i18n")),
    # API del monolito. Se expone también bajo el prefijo versionado /api/v1/
    # para que Nginx pueda enrutar explícitamente las rutas "legacy" a Django,
    # mientras las rutas estranguladas (/api/v2/...) van al microservicio Flask.
    # Se conserva /api/ sin versión por retrocompatibilidad con la Entrega 1.
    path("api/", include("interfaces.api.urls")),
    path("api/v1/", include(("interfaces.api.urls", "api"), namespace="api-v1")),
    # Frontend web (plantillas modernas con i18n).
    path("", include("interfaces.web.urls")),
]
