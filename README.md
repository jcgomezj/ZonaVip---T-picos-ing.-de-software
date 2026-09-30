# ZonaVip — Núcleo de Negocio y API (Entrega 1)

Proyecto de curso *Arquitectura de Software 2026*. Plataforma de reserva
de boletas para eventos por zonas/localidades (General, VIP, Palco,
Platea).

Documentación técnica completa (estructura de carpetas, diagrama de
secuencia, preparación para API Gateway, patrones creacionales) en
[`docs/wiki/Home.md`](docs/wiki/Home.md) — ver también la sección
**"Publicar esto en la Wiki de GitHub"** más abajo.

## Stack

- Python 3.11+
- Django 5.x
- Django REST Framework
- SQLite (desarrollo)

## Instalación y ejecución local

```bash
python -m venv .venv
source .venv/bin/activate          # Windows: .venv\Scripts\activate

pip install -r requirements.txt

python manage.py migrate
python manage.py createsuperuser   # opcional, para /admin/

python manage.py runserver
```

Para probar el flujo completo necesitas: un usuario organizador con
perfil `Organizador`, una `CategoriaEvento`, un `Evento` y al menos una
`Localidad`. La forma más rápida es crearlos desde `/admin/` con el
superusuario, o vía shell:

```bash
python manage.py shell
```
```python
from apps.usuarios.models import Usuario
from apps.eventos.models import CategoriaEvento, Organizador, Evento, Localidad
from django.utils import timezone
import datetime

promotor = Usuario.objects.create_user(username="promotora", password="clave12345")
organizador = Organizador.objects.create(usuario=promotor, nombre_empresarial="Promotora EAFIT")
categoria = Evento_categoria = CategoriaEvento.objects.create(nombre="Concierto")
evento = Evento.objects.create(
    organizador=organizador, categoria=categoria, titulo="Rock al Parque",
    lugar="Medellín", fecha_evento=timezone.now() + datetime.timedelta(days=30),
    estado=Evento.Estado.PUBLICADO,
)
Localidad.objects.create(evento=evento, nombre="VIP", precio=150000, cupo=50)
```

## Correr los tests

```bash
python manage.py test tests
```

10 tests (5 de dominio puro sobre `BoletaBuilder`, 5 de integración de la
API con el cliente de pruebas de DRF), todos en verde.

## Endpoints principales

| Método | Ruta | Auth | Descripción |
|---|---|---|---|
| `GET` | `/api/eventos/` | No | Lista eventos publicados |
| `POST` | `/api/eventos/` | Sí (organizador) | Crea un evento (`BORRADOR`) |
| `POST` | `/api/eventos/<id>/publicar/` | Sí (organizador) | Publica el evento |
| `POST` | `/api/boletas/reservar/` | Sí | Reserva una boleta |
| `POST` | `/api/boletas/<id>/cancelar/` | Sí | Cancela una boleta propia |
| `GET` | `/api/boletas/mias/` | Sí | Boletas del usuario autenticado |

Ejemplo de reserva:

```bash
curl -X POST http://localhost:8000/api/boletas/reservar/ \
  -u camilo:clave12345 \
  -H "Content-Type: application/json" \
  -d '{"evento_id": 1, "localidad_id": 1}'
```

Respuestas: `201` boleta creada · `400` datos inválidos · `404` evento o
localidad inexistente · `409` sin cupo disponible / operación no válida
para el estado actual.

## Arquitectura híbrida (Taller 02 — Strangler Pattern)

A partir del Taller 02, el módulo de **generación/validación de códigos QR**
se estranguló del monolito a un **microservicio Flask** independiente. Nginx
orquesta el tráfico: las rutas legacy (`/`, `/api/v1/`) van a Django y la ruta
estrangulada (`/api/v2/qr/`) va a Flask.

```bash
# Levantar toda la topología: Django + Flask + PostgreSQL + Nginx
docker compose up --build

curl http://localhost/api/v1/eventos/     # -> Django (monolito)
curl http://localhost/api/v2/qr/health    # -> Flask (microservicio)
```

Documentación completa, matriz de decisión y diagrama de la nueva arquitectura:
[`docs/wiki/05-Migracion-a-Microservicios.md`](docs/wiki/05-Migracion-a-Microservicios.md).
El código del microservicio y su README están en
[`services/qr_service/`](services/qr_service/).

## Variable de entorno relevante

`ENV_TYPE` — controla qué `Notificador` instancia `NotificadorFactory`:

```bash
ENV_TYPE=MOCK  python manage.py runserver   # ConsolaNotificador (por defecto)
ENV_TYPE=REAL  python manage.py runserver   # EmailNotificador
```


