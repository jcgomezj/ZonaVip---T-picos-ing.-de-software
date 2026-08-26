from django.contrib import admin
from django.contrib.auth.admin import UserAdmin

from apps.usuarios.models import Usuario

admin.site.register(Usuario, UserAdmin)
