# 1. Justificación de la estructura de carpetas

```
zonavip_project/
├── manage.py
├── config/              # Configuración de Django (settings, urls raíz, wsgi/asgi)
├── apps/                # SOLO persistencia: modelos Django, uno por app
│   ├── usuarios/
│   ├── eventos/
│   └── boletas/
├── domain/              # Lógica de negocio pura, sin dependencia de Django
│   ├── exceptions.py     (jerarquía de errores de dominio)
│   └── builders/
│       └── boleta_builder.py
├── application/         # Service Layer: orquesta los flujos de negocio
│   └── services.py
├── infra/               # Adaptadores hacia el "mundo exterior"
│   ├── factories/
│   │   └── notificador_factory.py
│   └── notificadores/
├── interfaces/          # Capa de presentación (DRF)
│   └── api/
│       ├── serializers.py
│       ├── views.py
│       └── urls.py
├── tests/
└── docs/wiki/
```

## Por qué esta organización (por capa, no solo por app)

Django, "out of the box", empuja a organizar todo por *app* (cada app con
su propio `models.py`, `views.py`, `services.py`...). Para este proyecto
elegimos combinar eso con una segunda dimensión, **por capa
arquitectónica**, porque el requisito explícito de la entrega es
**desacoplamiento total** entre dominio, orquestación y presentación:

- **`apps/`** — Cada app de Django (`usuarios`, `eventos`, `boletas`)
  contiene *exclusivamente* modelos: tipos de dato, constraints,
  relaciones y métodos de persistencia. No hay reglas de negocio aquí;
  el único método "activo" (`Localidad.hay_cupo()`) es una lectura
  booleana derivada de columnas persistidas, no un cálculo de negocio.

- **`domain/`** — Contiene las reglas de negocio que **no necesitan
  Django para existir**: el `BoletaBuilder` recibe una `localidad`
  cualquiera que cumpla un contrato mínimo (`.id`, `.precio`,
  `.hay_cupo()`), por lo que se puede testear con un objeto falso sin
  tocar la base de datos (ver `tests/test_boleta_builder.py`, que corre
  sin fixtures ni BD). También vive aquí `exceptions.py`, el vocabulario
  de errores de negocio, independiente de HTTP.

- **`application/`** — El Service Layer. Es la única capa que conoce
  tanto al dominio (`domain/`) como a la persistencia (`apps/`) y a la
  infraestructura (`infra/`). Cada clase orquesta un único flujo de
  negocio de punta a punta dentro de una transacción atómica
  (`@transaction.atomic`).

- **`infra/`** — Adaptadores hacia dependencias externas
  (notificaciones hoy; pasarela de pagos o generador de reportes en la
  próxima entrega). Se seleccionan mediante Factory, nunca con `if`
  dispersos en el Service.

- **`interfaces/`** — La capa de presentación (DRF). Solo sabe
  serializar/deserializar y traducir excepciones de dominio a códigos
  HTTP. No importa nada de `infra/` ni instancia modelos directamente.

## Regla de dependencia (una sola dirección)

```
interfaces  →  application  →  domain
                    ↓
                  apps (ORM) , infra (adaptadores)
```

`domain/` no importa nada de `apps/`, `infra/` ni `interfaces/`. Esto es
lo que permite, por ejemplo, cambiar Django Rest Framework por otro
framework de presentación, o SQLite por otro motor, sin reescribir una
sola regla de negocio.

## Consecuencia práctica para la rúbrica

- **"Prohibido lógica de negocio en Views o Serializers"** → se cumple
  porque físicamente esas clases están en `interfaces/`, que no importa
  `domain/` directamente, solo a través de `application/`.
- **"Prohibido lógica de negocio en métodos del Model que no sean de
  persistencia"** → se cumple porque los modelos en `apps/` no conocen
  `BoletaBuilder`, `NotificadorFactory` ni las excepciones de dominio.
