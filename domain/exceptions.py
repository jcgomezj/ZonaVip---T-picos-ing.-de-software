"""
Jerarquía de excepciones de dominio.

NO conocen HTTP ni DRF: son vocabulario de negocio. La capa de interfaces
las traduce a códigos HTTP. Cada una lleva un `codigo` estable legible por
máquina, además del mensaje para humanos.
"""


class DomainError(Exception):
    """Excepción base para cualquier error de reglas de negocio de ZonaVip."""

    codigo = "error_dominio"

    def __init__(self, mensaje: str = "", *, codigo: str | None = None, **extra):
        super().__init__(mensaje)
        if codigo:
            self.codigo = codigo
        self.extra = extra  # datos serializables extra (p. ej. `usada_en`)


class ValidacionNegocioError(DomainError):
    """Datos incompletos o que violan una regla. -> HTTP 400."""

    codigo = "validacion"


class PagoRechazadoError(DomainError):
    """La pasarela rechazó el cobro. -> HTTP 402."""

    codigo = "pago_rechazado"


class PermisoDenegadoError(DomainError):
    """Autenticado pero sin permiso sobre el recurso. -> HTTP 403."""

    codigo = "permiso_denegado"


class RecursoNoEncontradoError(DomainError):
    """La entidad solicitada no existe. -> HTTP 404."""

    codigo = "no_encontrado"


class ConflictoEstadoError(DomainError):
    """Válida en forma, pero imposible dado el estado actual. -> HTTP 409."""

    codigo = "conflicto_estado"


class BoletaYaUsadaError(ConflictoEstadoError):
    """La boleta ya fue validada en el ingreso."""

    codigo = "ya_usada"
