from django.contrib import admin

from apps.boletas.models import Boleta


@admin.register(Boleta)
class BoletaAdmin(admin.ModelAdmin):
    list_display = ("codigo_qr", "usuario", "evento", "localidad", "estado", "precio")
    list_filter = ("estado",)
    readonly_fields = ("codigo_qr", "reservada_en", "creado_en")
