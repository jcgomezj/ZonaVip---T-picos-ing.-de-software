from django.contrib import admin

from apps.eventos.models import CategoriaEvento, Evento, Localidad, Organizador


class LocalidadInline(admin.TabularInline):
    model = Localidad
    extra = 1


@admin.register(Evento)
class EventoAdmin(admin.ModelAdmin):
    list_display = ("titulo", "organizador", "categoria", "fecha_evento", "estado")
    list_filter = ("estado", "categoria")
    inlines = [LocalidadInline]


admin.site.register(CategoriaEvento)
admin.site.register(Organizador)
