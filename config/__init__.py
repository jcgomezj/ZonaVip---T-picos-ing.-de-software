"""
Al arrancar Django, importamos la app de Celery para que el decorador
`@shared_task` quede disponible en todas las apps y el worker la descubra.
"""

from .celery import app as celery_app

__all__ = ("celery_app",)
