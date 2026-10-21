"""
Datos de ejemplo de ZonaVip (idempotente).

Crea / sincroniza:
  - El usuario administrador del backend. Las credenciales NO están en el
    código ni en la UI: se leen de variables de entorno
        ZONAVIP_ADMIN_USER      (por defecto "admin")
        ZONAVIP_ADMIN_EMAIL     (por defecto "admin@zonavip.co")
        ZONAVIP_ADMIN_PASSWORD  (si falta y el usuario es nuevo, se genera una
                                 contraseña aleatoria y se muestra UNA vez)
    o de los argumentos --admin-user / --admin-password.
  - 10 eventos publicados (3 originales + 7 nuevos: 3 conciertos y 4
    festivales) con imágenes locales, fechas, recintos y precios por localidad.

Uso:
    python manage.py seed_demo
    python manage.py seed_demo --reset   # borra eventos SIN boletas y recrea

Se puede ejecutar varias veces: los eventos se identifican por título y no se
duplican. Nunca se borran localidades que ya tengan boletas vendidas.
"""

from __future__ import annotations

import datetime
import os
import secrets

from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand
from django.utils import timezone

from apps.eventos.models import CategoriaEvento, Evento, Localidad, Organizador

Usuario = get_user_model()

IMG = "/static/web/img/eventos/{}.jpg"
ESTADIO, ABIERTO, CERRADO = (
    Evento.TipoRecinto.ESTADIO,
    Evento.TipoRecinto.ABIERTO,
    Evento.TipoRecinto.CERRADO,
)


def tribunas(base: int) -> list[tuple]:
    """Las 10 localidades de un estadio. `base` = precio de la tribuna popular.

    (nombre, tipo, precio, cupo, vendidas)
    """
    return [
        ("Norte", "GENERAL", base, 4000, 2600),
        ("Norte Baja", "GENERAL", int(base * 1.25), 2500, 1900),
        ("Sur", "GENERAL", base, 4000, 2450),
        ("Sur Baja", "GENERAL", int(base * 1.25), 2500, 1750),
        ("Occidental", "PLATEA", int(base * 2.0), 3000, 2700),
        ("Occidental Alta", "PLATEA", int(base * 1.6), 3500, 2200),
        ("Oriental", "GENERAL", int(base * 1.5), 3000, 1800),
        ("Oriental Alta", "GENERAL", int(base * 1.15), 3500, 1500),
        ("Gramilla", "GENERAL", int(base * 2.6), 6000, 5200),
        ("VIP", "VIP", int(base * 5.0), 400, 372),
    ]


def gramilla(precio: int, cupo: int, vendidas: int) -> list[tuple]:
    return [("Gramilla / General", "GENERAL", precio, cupo, vendidas)]


EVENTOS = [
    # ------------------------- Originales ------------------------------
    {
        "cat": "Concierto", "titulo": "Neon Dreams Live",
        "lugar": "Movistar Arena, Bogotá", "dias": 18, "recinto": CERRADO,
        "img": "https://images.unsplash.com/photo-1540039155733-5bb30b53aa14?w=1200&q=75&auto=format&fit=crop",
        "locs": [("General", "GENERAL", 120000, 800, 540), ("VIP", "VIP", 390000, 120, 103)],
    },
    {
        "cat": "Festival", "titulo": "Aurora Fest 2026",
        "lugar": "Parque Norte, Medellín", "dias": 32, "recinto": ABIERTO,
        "img": "https://images.unsplash.com/photo-1493225457124-a3eb161ffa5f?w=1200&q=75&auto=format&fit=crop",
        # Parque abierto: localidad única. "General" se renombra si ya existía.
        "renombrar": {"General": "Gramilla / General"},
        "locs": gramilla(180000, 1500, 980),
    },
    {
        "cat": "Concierto", "titulo": "Midnight Pulse Tour",
        "lugar": "Teatro Metropolitano, Medellín", "dias": 45, "recinto": CERRADO,
        "img": "https://images.unsplash.com/photo-1429962714451-bb934ecdc4ec?w=1200&q=75&auto=format&fit=crop",
        "locs": [("General", "GENERAL", 95000, 600, 210), ("VIP", "VIP", 280000, 90, 61)],
    },
    # ------------------------- 3 conciertos nuevos ---------------------
    {
        "cat": "Concierto", "titulo": "Karol G · Tropicoqueta Tour",
        "lugar": "Estadio Atanasio Girardot, Medellín", "dias": 60, "recinto": ESTADIO,
        "img": IMG.format("tropicoqueta"),
        "desc": "La Bichota llena el Atanasio Girardot con su gira más grande.",
        "locs": tribunas(140000),
    },
    {
        "cat": "Concierto", "titulo": "Feid · Ferxxo Nitro Jam",
        "lugar": "Estadio Nemesio Camacho El Campín, Bogotá", "dias": 75, "recinto": ESTADIO,
        "img": IMG.format("urban-stadium"),
        "desc": "Una noche verde de reguetón y pirotecnia en El Campín.",
        "locs": tribunas(130000),
    },
    {
        "cat": "Concierto", "titulo": "Rosalía · Lux en Vivo",
        "lugar": "Movistar Arena, Bogotá", "dias": 52, "recinto": CERRADO,
        "img": IMG.format("arena-pop"),
        "desc": "Show íntimo en escenario circular, con producción de arena.",
        "locs": [
            ("General", "GENERAL", 210000, 3000, 1900),
            ("Platea", "PLATEA", 340000, 1500, 1200),
            ("VIP", "VIP", 720000, 250, 190),
        ],
    },
    # ------------------------- 4 festivales nuevos ---------------------
    {
        "cat": "Festival", "titulo": "Ritvales 2026",
        "lugar": "Parque Norte, Medellín", "dias": 90, "recinto": ABIERTO,
        "img": IMG.format("ritvales"),
        "desc": "Festival de música electrónica con ritual de luces y láseres.",
        "locs": gramilla(260000, 9000, 5600),
    },
    {
        "cat": "Festival", "titulo": "EDC Colombia",
        "lugar": "Autódromo de Tocancipá, Cundinamarca", "dias": 110, "recinto": ABIERTO,
        "img": IMG.format("edc"),
        "desc": "Electric Daisy Carnival: tres escenarios, rueda de la fortuna y fuegos artificiales.",
        "locs": gramilla(420000, 25000, 18800),
    },
    {
        "cat": "Festival", "titulo": "Festival Estéreo Picnic",
        "lugar": "Parque Simón Bolívar, Bogotá", "dias": 130, "recinto": ABIERTO,
        "img": IMG.format("picnic"),
        "desc": "Música alternativa, electrónica y pop al atardecer, en pleno parque.",
        "locs": gramilla(350000, 30000, 21500),
    },
    {
        "cat": "Festival", "titulo": "Medellín Urban Fest",
        "lugar": "Estadio Atanasio Girardot, Medellín", "dias": 150, "recinto": ESTADIO,
        "img": IMG.format("urban-fest"),
        "desc": "Trap, reguetón, hip-hop y electrónica urbana en el estadio.",
        "locs": tribunas(120000),
    },
]


class Command(BaseCommand):
    help = "Crea el admin (por entorno) y el catálogo de eventos de ejemplo."

    def add_arguments(self, parser):
        parser.add_argument("--reset", action="store_true",
                            help="Borra los eventos sin boletas antes de recrear.")
        parser.add_argument("--admin-user", default=os.environ.get("ZONAVIP_ADMIN_USER", "admin"))
        parser.add_argument("--admin-email",
                            default=os.environ.get("ZONAVIP_ADMIN_EMAIL", "admin@zonavip.co"))
        parser.add_argument("--admin-password",
                            default=os.environ.get("ZONAVIP_ADMIN_PASSWORD", ""))

    # ------------------------------------------------------------------
    def _admin(self, opts) -> Usuario:
        user, creado = Usuario.objects.get_or_create(
            username=opts["admin_user"], defaults={"email": opts["admin_email"]}
        )
        password = opts["admin_password"]
        if not password and creado:
            password = secrets.token_urlsafe(12)
            self.stdout.write(self.style.WARNING(
                f"Contraseña generada para '{user.username}' (guárdala, no se vuelve a mostrar): {password}"
            ))
        if password:
            user.set_password(password)
        user.is_staff = user.is_superuser = True
        if not user.email:
            user.email = opts["admin_email"]
        user.save()
        estado = "creado" if creado else ("actualizado" if opts["admin_password"] else "sin cambios")
        self.stdout.write(self.style.SUCCESS(f"Administrador '{user.username}' {estado}."))
        return user

    def _sync_localidades(self, evento: Evento, data: dict) -> None:
        for viejo, nuevo in data.get("renombrar", {}).items():
            if not evento.localidades.filter(nombre=nuevo).exists():
                evento.localidades.filter(nombre=viejo).update(nombre=nuevo)

        nombres = []
        for nombre, tipo, precio, cupo, vendidas in data["locs"]:
            nombres.append(nombre)
            loc, creada = Localidad.objects.get_or_create(
                evento=evento, nombre=nombre,
                defaults={"tipo": tipo, "precio": precio, "cupo": cupo, "vendidas": vendidas},
            )
            if not creada:
                # Mantiene lo ya vendido; solo asegura tipo/precio y un cupo válido.
                loc.tipo, loc.precio = tipo, precio
                loc.cupo = max(cupo, loc.vendidas)
                loc.save(update_fields=["tipo", "precio", "cupo"])

        # Localidades que ya no existen en el catálogo: solo si no tienen boletas.
        sobrantes = evento.localidades.exclude(nombre__in=nombres)
        for loc in sobrantes:
            if loc.boletas.exists():
                self.stdout.write(self.style.WARNING(
                    f"  · '{loc.nombre}' de {evento.titulo} se conserva (tiene boletas)."))
            else:
                loc.delete()

    def handle(self, *args, **options):
        admin = self._admin(options)
        organizador, _ = Organizador.objects.get_or_create(
            usuario=admin, defaults={"nombre_empresarial": "ZV Events", "verificado": True}
        )

        if options["reset"]:
            borrados = Evento.objects.filter(boletas__isnull=True).delete()[0]
            self.stdout.write(self.style.WARNING(
                f"Eventos sin boletas eliminados (incluye relacionados): {borrados}"))

        for data in EVENTOS:
            categoria, _ = CategoriaEvento.objects.get_or_create(nombre=data["cat"])
            evento, creado = Evento.objects.get_or_create(
                titulo=data["titulo"],
                defaults={
                    "organizador": organizador,
                    "categoria": categoria,
                    "descripcion": data.get("desc", "Evento de demostración para probar la experiencia de compra."),
                    "lugar": data["lugar"],
                    "fecha_evento": timezone.now() + datetime.timedelta(days=data["dias"]),
                    "estado": Evento.Estado.PUBLICADO,
                    "imagen": data["img"],
                    "tipo_recinto": data["recinto"],
                },
            )
            if not creado:
                evento.tipo_recinto = data["recinto"]
                evento.lugar = data["lugar"]
                evento.save(update_fields=["tipo_recinto", "lugar"])
            self._sync_localidades(evento, data)
            self.stdout.write(self.style.SUCCESS(
                f"{'Creado' if creado else 'Sincronizado'}: {evento.titulo} [{data['recinto']}]"))

        self.stdout.write(self.style.SUCCESS("\n¡Listo! Abre http://localhost:8000/"))
