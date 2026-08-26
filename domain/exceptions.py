"""
Jerarquía de excepciones de dominio.

Estas excepciones NO conocen HTTP ni Django REST Framework: son puro
vocabulario de negocio. La capa de interfaces (interfaces/api/views.py)
es la única responsable de traducirlas a códigos de estado HTTP.

Tener esta jerarquía centralizada es lo que permite, a futuro, exponer
el mismo contrato de errores detrás de un API Gateway sin reescribir
lógica de negocio (ver docs/wiki/03-API-Gateway.md).
"""


class DomainError(Exception):
    """Excepción base para cualquier error de reglas de negocio de ZonaVip."""


class ValidacionNegocioError(DomainError):
    """Los datos de entrada son incompletos o no cumplen una regla de negocio.

    Se traduce a HTTP 400 (Bad Request).
    """


class RecursoNoEncontradoError(DomainError):
    """La entidad de dominio solicitada no existe.

    Se traduce a HTTP 404 (Not Found).
    """


class ConflictoEstadoError(DomainError):
    """La operación es válida en su forma, pero no es posible dado el estado
    actual del recurso (sin cupo, evento ya publicado, boleta ya cancelada, etc.).

    Se traduce a HTTP 409 (Conflict).
    """
