# Wiki Técnica — ZonaVip (Entrega 1)

**Curso:** Arquitectura de Software 2026 — Prof. Nicolás Ramírez Vélez
**Entrega:** No. 1 — Núcleo de Negocio y Exposición de API Profesional

ZonaVip es una plataforma de venta y reserva de boletas para eventos
(conciertos, teatro, deportivos), organizada por zonas/localidades
(General, VIP, Palco, Platea) con cupo limitado.

## Contenido de esta wiki

1. [Estructura de carpetas](01-Estructura-de-Carpetas.md) — por qué el
   proyecto se organiza por capas y no solo por apps de Django.
2. [Diagrama de secuencia](02-Diagrama-de-Secuencia.md) — flujo completo
   de la funcionalidad más compleja: **reservar una boleta**.
3. [Preparación para API Gateway](03-API-Gateway.md) — visión de
   escalabilidad de la capa de presentación.
4. [Patrones creacionales](04-Patrones-Creacionales.md) — justificación
   de Builder (Boleta) y Factory (Notificador).

## Estado del dominio en esta entrega

De las clases identificadas en el modelo de dominio, se implementó el
**60%** (6 de 10):

| Clase | Estado | Ubicación |
|---|---|---|
| `Usuario` | ✅ Implementada | `apps/usuarios/models.py` |
| `CategoriaEvento` | ✅ Implementada | `apps/eventos/models.py` |
| `Organizador` | ✅ Implementada | `apps/eventos/models.py` |
| `Evento` | ✅ Implementada | `apps/eventos/models.py` |
| `Localidad` | ✅ Implementada | `apps/eventos/models.py` |
| `Boleta` | ✅ Implementada (entidad más compleja) | `apps/boletas/models.py` |
| `Pago` | ⏳ Diseñada, pendiente para Entrega 2 | — |
| `CuponDescuento` | ⏳ Diseñada, pendiente para Entrega 2 | — |
| `Resena` | ⏳ Diseñada, pendiente para Entrega 2 | — |
| `Notificacion` (log persistente) | ⏳ Diseñada, pendiente para Entrega 2 | — |

`Pago` es intencionalmente la siguiente pieza a construir: hoy
`NotificadorFactory` ya resuelve una dependencia externa (notificaciones);
en la Entrega 2 se añadirá una `PasarelaPagoFactory` análoga, sin tocar
`ReservaBoletaService`.

## Flujos de negocio (Service Layer)

| Servicio | Responsabilidad única | Endpoint |
|---|---|---|
| `CrearEventoService` | Un organizador crea un evento en `BORRADOR` | `POST /api/eventos/` |
| `PublicarEventoService` | `BORRADOR` → `PUBLICADO` | `POST /api/eventos/<id>/publicar/` |
| `ReservaBoletaService` | Reserva una boleta (Builder + descuenta cupo + notifica) | `POST /api/boletas/reservar/` |
| `CancelarBoletaService` | Cancela una boleta y libera el cupo | `POST /api/boletas/<id>/cancelar/` |
