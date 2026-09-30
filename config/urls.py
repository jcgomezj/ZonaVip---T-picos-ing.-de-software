from django.contrib import admin
from django.urls import include, path

urlpatterns = [
    path("admin/", admin.site.urls),
    # API del monolito. Se expone también bajo el prefijo versionado /api/v1/
    # para que Nginx pueda enrutar explícitamente las rutas "legacy" a Django,
    # mientras las rutas estranguladas (/api/v2/...) van al microservicio Flask.
    # Se conserva /api/ sin versión por retrocompatibilidad con la Entrega 1.
    path("api/", include("interfaces.api.urls")),
    path("api/v1/", include(("interfaces.api.urls", "api"), namespace="api-v1")),
]
