from django.contrib import admin

from apps.boletas.models import Boleta, Pago


@admin.register(Boleta)
class BoletaAdmin(admin.ModelAdmin):
    list_display = ("codigo_qr", "usuario", "evento", "localidad", "estado", "precio", "usada_en")
    list_filter = ("estado", "motivo_cancelacion")
    search_fields = ("codigo_qr", "usuario__username", "usuario__email")
    readonly_fields = ("codigo_qr", "reservada_en", "creado_en", "usada_en", "validada_por")


@admin.register(Pago)
class PagoAdmin(admin.ModelAdmin):
    list_display = ("referencia", "usuario", "evento", "cantidad", "monto", "estado", "creado_en")
    list_filter = ("estado", "metodo")
    search_fields = ("referencia", "idempotency_key", "usuario__username")
    readonly_fields = ("referencia", "idempotency_key", "creado_en")
