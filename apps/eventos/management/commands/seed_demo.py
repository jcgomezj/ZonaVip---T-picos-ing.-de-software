"""
Comando de datos de ejemplo para probar la experiencia de usuario.

Crea:
  - Un usuario de prueba (admin / zonavip2026) con acceso al panel privado.
  - 3 eventos publicados con fotos de conciertos y localidades (General + VIP),
    listos para recorrer el flujo de compra desde el frontend.

Uso:
    python manage.py seed_demo
    python manage.py seed_demo --reset   # borra eventos previos y recrea
"""

from __future__ import annotations

import datetime

from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand
from django.utils import timezone

from apps.eventos.models import CategoriaEvento, Evento, Localidad, Organizador

Usuario = get_user_model()

# Imágenes de conciertos (Unsplash, libres de uso).
IMGS = [
    "https://images.unsplash.com/photo-1540039155733-5bb30b53aa14?w=1200&q=75&auto=format&fit=crop",
    "https://images.unsplash.com/photo-1493225457124-a3eb161ffa5f?w=1200&q=75&auto=format&fit=crop",
    "https://images.unsplash.com/photo-1429962714451-bb934ecdc4ec?w=1200&q=75&auto=format&fit=crop",
]

EVENTOS = [
    {
        "cat": "Concierto",
        "titulo": "Neon Dreams Live",
        "lugar": "Movistar Arena, Bogotá",
        "dias": 18,
        "img": IMGS[0],
        "locs": [("General", "GENERAL", 120000, 800, 540), ("VIP", "VIP", 390000, 120, 103)],
    },
    {
        "cat": "Festival",
        "titulo": "Aurora Fest 2026",
        "lugar": "Parque Norte, Medellín",
        "dias": 32,
        "img": IMGS[1],
        "locs": [("General", "GENERAL", 180000, 1500, 980), ("Palco", "PALCO", 520000, 60, 44)],
    },
    {
        "cat": "Concierto",
        "titulo": "Midnight Pulse Tour",
        "lugar": "Teatro Metropolitano, Medellín",
        "dias": 45,
        "img": IMGS[2],
        "locs": [("General", "GENERAL", 95000, 600, 210), ("VIP", "VIP", 280000, 90, 61)],
    },
]


class Command(BaseCommand):
    help = "Crea un usuario de prueba y 3 eventos de demostración."

    def add_arguments(self, parser):
        parser.add_argument(
            "--reset", action="store_true",
            help="Borra los eventos existentes antes de crear los de ejemplo.",
        )

    def handle(self, *args, **options):
        # --- Usuario de prueba (acceso al panel privado) ---
        user, creado = Usuario.objects.get_or_create(
            username="admin",
            defaults={"is_staff": True, "is_superuser": True, "email": "admin@zonavip.co"},
        )
        user.set_password("zonavip2026")
        user.is_staff = True
        user.is_superuser = True
        user.save()
        self.stdout.write(self.style.SUCCESS(
            f"Usuario de prueba {'creado' if creado else 'actualizado'}: admin / zonavip2026"
        ))

        organizador, _ = Organizador.objects.get_or_create(
            usuario=user, defaults={"nombre_empresarial": "ZV Events", "verificado": True}
        )

        if options["reset"]:
            borrados = Evento.objects.count()
            Evento.objects.all().delete()
            self.stdout.write(self.style.WARNING(f"Eventos borrados: {borrados}"))

        if Evento.objects.exists():
            self.stdout.write(self.style.WARNING(
                "Ya existen eventos; usa --reset para recrearlos. No se crearon nuevos."
            ))
            return

        for data in EVENTOS:
            categoria, _ = CategoriaEvento.objects.get_or_create(nombre=data["cat"])
            evento = Evento.objects.create(
                organizador=organizador,
                categoria=categoria,
                titulo=data["titulo"],
                descripcion="Evento de demostración para probar la experiencia de compra.",
                lugar=data["lugar"],
                fecha_evento=timezone.now() + datetime.timedelta(days=data["dias"]),
                estado=Evento.Estado.PUBLICADO,
                imagen=data["img"],
            )
            for nombre, tipo, precio, cupo, vendidas in data["locs"]:
                Localidad.objects.create(
                    evento=evento, nombre=nombre, tipo=tipo,
                    precio=precio, cupo=cupo, vendidas=vendidas,
                )
            self.stdout.write(self.style.SUCCESS(f"Evento creado: {evento.titulo}"))

        self.stdout.write(self.style.SUCCESS(
            "\n¡Listo! Entra a http://localhost:8000/ y prueba la compra. "
            "Panel privado: inicia sesión con admin / zonavip2026."
        ))
