"""
Instancia de Celery para ZonaVip (Entrega 2).

Celery + Redis implementan la **comunicación asíncrona** exigida por la
rúbrica: tareas pesadas (reportes, notificaciones) se encolan en el broker
(Redis) y las procesa un worker separado, sin bloquear el ciclo
request/response de Django.
"""

import os

from celery import Celery

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings")

app = Celery("zonavip")

# Lee la configuración desde settings.py (todas las claves con prefijo CELERY_).
app.config_from_object("django.conf:settings", namespace="CELERY")

# Descubre automáticamente los módulos tasks.py de las apps instaladas.
app.autodiscover_tasks()


@app.task(bind=True)
def debug_task(self):
    print(f"Request: {self.request!r}")
