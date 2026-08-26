# 3. Cómo el sistema está preparado para un API Gateway

Un API Gateway (Kong, AWS API Gateway, NGINX, etc.) se ubica delante de
uno o varios servicios y centraliza preocupaciones transversales:
enrutamiento, autenticación/autorización, *rate limiting*, agregación de
respuestas y traducción de errores. El diseño actual de ZonaVip anticipa
ese escenario en varios puntos:

## 1. Contrato de errores uniforme (ya centralizado hoy)

Toda la API responde errores con la misma forma:

```json
{ "error": "mensaje legible del problema" }
```

y el mismo código HTTP siempre significa lo mismo en cualquier endpoint:

| Código | Excepción de dominio | Significado |
|---|---|---|
| `400` | `ValidacionNegocioError` | Datos inválidos o incompletos |
| `404` | `RecursoNoEncontradoError` | La entidad no existe |
| `409` | `ConflictoEstadoError` | Estado actual no permite la operación |

Esto se logra con un único punto de traducción
(`_respuesta_error_dominio()` en `interfaces/api/views.py`) en vez de
manejar excepciones de forma distinta en cada vista. Un Gateway que
agregue respuestas de varios microservicios (por ejemplo, `zonavip-core`
+ un futuro `zonavip-pagos`) puede confiar en ese contrato sin necesitar
lógica especial por servicio.

## 2. Rutas versionables y namespaced

`interfaces/api/urls.py` ya vive bajo un `app_name = "api"` y se monta
en `config/urls.py` bajo el prefijo `/api/`. Migrar a `/api/v1/` (o
publicar `/api/v2/` en paralelo cuando cambien los contratos) es un
cambio de una línea en `config/urls.py`, sin tocar `interfaces/api/`.

## 3. Autenticación desacoplada de la lógica de negocio

Los `Service` reciben identificadores (`usuario_id`, `organizador_id`)
como datos simples, nunca el objeto `request` de Django. Esto significa
que, si el Gateway pasa a resolver la identidad del usuario (por
ejemplo, validando un JWT y reenviando el `user_id` en un header), el
único punto que cambia es la vista (de dónde saca el `usuario_id`), no
los servicios ni el dominio.

## 4. Statelessness

Cada request de `ReservarBoletaView`, `CancelarBoletaView`, etc., es
autocontenida: no depende de estado en memoria del proceso Django (todo
el estado vive en la base de datos). Esto permite escalar
horizontalmente detrás de un balanceador/Gateway sin *sticky sessions*
para estas operaciones.

## 5. Camino hacia microservicios

La separación en `domain/` / `application/` / `infra/` / `interfaces/`
(ver [Estructura de carpetas](01-Estructura-de-Carpetas.md)) significa
que, si en el futuro `boletas` se extrae a un servicio independiente de
`eventos`, el Service Layer y el Builder ya están aislados del resto:
solo cambiaría cómo `LocalidadRepository` obtiene la localidad (¿ORM
local, o una llamada HTTP/gRPC al servicio de eventos?), sin tocar
`BoletaBuilder` ni las reglas de negocio de la reserva.

## Qué falta (fuera del alcance de esta entrega)

- Autenticación real vía JWT/OAuth2 delegada al Gateway.
- *Rate limiting* y *circuit breaking* (responsabilidad del Gateway, no
  de la aplicación).
- Versionado explícito de la API (`/api/v1/`) — trivial de añadir dado
  el punto 2, pero no era requisito de esta entrega.
