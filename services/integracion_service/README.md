# Microservicio de Integración — ZonaVip (Entrega 2)

Segundo microservicio estrangulado del monolito. Concentra las tres
responsabilidades de **integración** de la Entrega 2, aplicando el **Patrón
Adapter** y la **Inversión de Dependencias (DIP)**.

> Documentación arquitectónica: [`docs/wiki/06-Entrega2-Integracion-y-Resiliencia.md`](../../docs/wiki/06-Entrega2-Integracion-y-Resiliencia.md)

## Responsabilidades

| # | Requisito de la rúbrica | Endpoint (tras Nginx) |
|---|---|---|
| 1 | **Servicio a proveer** (JSON del sistema) | `GET /api/v2/integracion/info` |
| 2 | **Consumo de API de terceros vía Adapter** | `GET /api/v2/integracion/clima` |
| 3 | **Consumo del servicio del equipo aliado** | `GET /api/v2/integracion/aliado` |

## Patrón Adapter + Inversión de Dependencias

```
application/services.py   ──depende de──►  domain/ports.py  (interfaces)
                                                 ▲
                                                 │ implementan
                          ┌──────────────────────┴───────────────────────┐
         infra/open_meteo_adapter.py                      infra/aliado_adapter.py
         (API de terceros: Open-Meteo)                    (servicio del aliado)
```

El núcleo (`application/`) **solo conoce las interfaces** de `domain/ports.py`.
Los adaptadores concretos viven en `infra/` y se inyectan en `crear_app()`.
Cambiar de proveedor de clima o de URL del aliado **no toca la lógica de
negocio**, solo el adaptador o su configuración.

## Resiliencia

El adaptador del aliado degrada con elegancia: si el aliado no responde
(timeout/5xx/red caída) **no propaga la excepción**, devuelve
`{"disponible": false, "error": "..."}` para que la UI no se rompa.

## Variables de entorno

| Variable | Default | Descripción |
|---|---|---|
| `ALIADO_API_URL` | *(vacío)* | URL del endpoint del equipo aliado |
| `HTTP_TIMEOUT` | `5` | Timeout (s) de las llamadas HTTP salientes |

## Ejecutar en local

```bash
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
python app.py   # http://localhost:5001/api/v2/integracion/health
```

## Tests

```bash
pip install -r requirements.txt pytest
pytest
```

6 pruebas con dobles de prueba (fakes) que implementan los puertos — se prueba
la lógica **sin llamar a ninguna API externa real**, demostrando el valor del
Adapter.
