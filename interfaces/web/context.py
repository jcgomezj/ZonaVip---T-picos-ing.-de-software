"""Context processor: roles que habilitan opciones del menú."""

from apps.eventos.models import Organizador


def roles(request):
    user = getattr(request, "user", None)
    if not (user and user.is_authenticated):
        return {"es_organizador": False, "puede_checkin": False}
    es_org = Organizador.objects.filter(usuario_id=user.pk).exists()
    return {"es_organizador": es_org, "puede_checkin": bool(user.is_staff or es_org)}
