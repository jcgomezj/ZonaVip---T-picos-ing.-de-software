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
python manage.py seed_demo         # 10 eventos de demo + usuario admin (ver abajo)

python manage.py runserver
```

`seed_demo` crea el administrador `admin` con la contraseña de la variable
`ZONAVIP_ADMIN_PASSWORD` (o genera una aleatoria y la muestra una vez). Para
cambiarla: `python manage.py changepassword admin`.

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

79 tests en verde: dominio puro (`BoletaBuilder`), integración de la API con el
cliente de pruebas de DRF, flujo web, pagos con idempotencia, check-in,
cancelación de evento con Celery (en modo *eager*), expiración de reservas,
panel de organizador, exportación CSV de asistentes, resiliencia ante el
broker caído, páginas de error y permisos.

## Endpoints principales

| Método | Ruta | Auth | Descripción |
|---|---|---|---|
| `GET` | `/api/eventos/` | No | Lista eventos publicados |
| `POST` | `/api/eventos/` | Sí (organizador) | Crea un evento (`BORRADOR`) |
| `POST` | `/api/eventos/<id>/publicar/` | Sí (organizador) | Publica el evento |
| `POST` | `/api/boletas/reservar/` | Sí | Reserva una boleta (retiene cupo `RESERVA_TTL_MINUTOS`) |
| `POST` | `/api/boletas/comprar/` | Sí | Cobra y emite N boletas `PAGADA`. Cabecera `Idempotency-Key` |
| `POST` | `/api/boletas/<id>/pagar/` | Sí (dueño) | Paga una reserva vigente |
| `POST` | `/api/boletas/<id>/cancelar/` | Sí (dueño) | Cancela una boleta propia (reembolsa si estaba pagada) |
| `POST` | `/api/boletas/validar/` | Staff u organizador del evento | **Check-in**: `PAGADA → USADA` |
| `GET` | `/api/boletas/mias/` | Sí | Boletas del usuario autenticado |
| `POST` | `/api/eventos/<id>/cancelar/` | Organizador del evento / admin | Cancela evento y boletas, reembolsa, avisa por correo (Celery) |
| `GET` | `/api/organizador/resumen/` | Organizador / admin | Ventas por localidad y ocupación |
| `GET` | `/health/` | No | Liveness/readiness (Django + BD) |
| `GET` | `/organizador/eventos/<id>/asistentes.csv` | Organizador del evento / admin (sesión web) | Descarga los asistentes (boletas pagadas/usadas) en CSV |

### Entrega 3: pagos, check-in y organizador

- **Pasarela simulada** (`infra/pagos/`, patrón Factory + puerto). No mueve
  dinero: el cliente envía un `token_pago` opaco y la pasarela decide
  (`tok_ok`, `tok_declinada`, `tok_fondos`, `tok_error`). Pago rechazado → `402`.
- **Idempotencia**: la misma `Idempotency-Key` del mismo usuario devuelve la
  compra original (`200` + `Idempotent-Replayed: true`) sin cobrar de nuevo.
- **Ciclo de la boleta**: `RESERVADA → PAGADA → USADA`; `CANCELADA` por el
  usuario, por cancelación del evento o por reserva vencida (tarea Celery beat
  cada minuto).
- **Check-in** (`/checkin/` en la web, `POST /api/boletas/validar/`): acepta el
  QR dinámico, el estático del correo o el código digitado; el segundo escaneo
  responde `409 ya_usada`. Con `CHECKIN_EXIGIR_QR_DINAMICO=True` solo el dinámico.
- **Panel del organizador** (`/organizador/`): ingresos, ocupación y asistencia
  por localidad; cancelar un evento desde ahí.
- **Errores uniformes**: `{"error": ..., "codigo": ..., ...}` con códigos
  estables (`sin_cupo`, `ya_usada`, `pago_rechazado`, `reserva_vencida`...).
- **Seguridad**: permisos `IsAuthenticatedOrReadOnly` por defecto; reportes,
  notificaciones y tareas solo admin; throttling DRF y `limit_req` en Nginx.

### Entrega final: asistentes CSV y preparación para producción

- **Exportar asistentes a CSV** (botón *Asistentes CSV* en `/organizador/`):
  código, asistente, correo, localidad, precio, estado, fecha de compra, hora
  de ingreso y quién la validó. Una sola consulta a la BD; el organizador solo
  exporta sus eventos (otro evento → `404`). Lleva BOM para que Excel muestre
  bien las tildes y neutraliza la *inyección de fórmulas* (celdas que empiezan
  por `=`, `+`, `-`, `@`).
- **Páginas de error propias** (`404.html` y `500.html`) para producción
  (`DEBUG=False`); la 500 es autónoma porque Django la pinta sin contexto.
- **Broker caído → `503 broker_no_disponible`** en reportes y notificaciones,
  en vez de dejar la petición colgada hasta el `502` de Nginx.
- **Catálogo EN completo**: se tradujeron los ~120 textos de las entregas 2 y 3
  que seguían solo en español, y se corrigieron 3 traducciones *fuzzy*
  (Django las ignora).

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

## Entrega 2 — Integración, Resiliencia e i18n

La Entrega 2 evoluciona ZonaVip a un **ecosistema híbrido y resiliente**:

- **Segundo microservicio Flask** (`services/integracion_service/`): expone una
  API JSON del sistema, consume el servicio de un **equipo aliado** y consume
  una **API de terceros** (clima, Open-Meteo) mediante el **Patrón Adapter**
  (Inversión de Dependencias).
- **Comunicación asíncrona** con **Celery + Redis** (Message Broker) para
  reportes y notificaciones en segundo plano (`apps/reportes/tasks.py`).
- **i18n bilingüe ES/EN** con `gettext` — sin textos quemados (`locale/`).
- **Frontend moderno** (Tailwind + Alpine.js, modo oscuro, responsive) en
  `interfaces/web/`: landing (`/`) y panel del sistema (`/panel/`).
- **Nginx como API Gateway** enrutando a los dos microservicios + el monolito.

```bash
# Ecosistema completo: Nginx + Django + 2 Flask + PostgreSQL + Redis + Celery
docker compose up --build -d

curl http://localhost/api/v2/integracion/info     # servicio a proveer
curl "http://localhost/api/v2/integracion/clima?ciudad=Medellin"  # terceros (Adapter)
```

- Arquitectura, diagrama y mapa de rúbrica: [`docs/wiki/06-Entrega2-Integracion-y-Resiliencia.md`](docs/wiki/06-Entrega2-Integracion-y-Resiliencia.md)
- **Guía de despliegue en AWS EC2:** [`docs/DEPLOY_AWS.md`](docs/DEPLOY_AWS.md)

### Tests de todo el ecosistema

```bash
python manage.py test tests                                   # 79 — monolito
cd services/qr_service && pytest                              # 10 — microservicio QR
cd services/integracion_service && pytest                     #  9 — microservicio Integración
```

## Variable de entorno relevante

`ENV_TYPE` — controla qué `Notificador` instancia `NotificadorFactory`:

```bash
ENV_TYPE=MOCK  python manage.py runserver   # ConsolaNotificador (por defecto)
ENV_TYPE=REAL  python manage.py runserver   # EmailNotificador
```


