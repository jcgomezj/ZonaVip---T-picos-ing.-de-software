# 2. Diagrama de secuencia — Reservar una boleta

Es la funcionalidad más compleja del sistema: involucra las cuatro capas,
un patrón Builder, un patrón Factory, control de concurrencia
(`select_for_update`) y tres posibles desenlaces HTTP (`201`, `404`,
`409`).

`POST /api/boletas/reservar/`

```mermaid
sequenceDiagram
    actor Cliente
    participant View as ReservarBoletaView (interfaces/api)
    participant Ser as ReservaBoletaInputSerializer
    participant Svc as ReservaBoletaService (application)
    participant Repo as LocalidadRepository
    participant Bld as BoletaBuilder (domain)
    participant ORM as BoletaRepository / ORM
    participant Fac as NotificadorFactory (infra)
    participant Not as ConsolaNotificador / EmailNotificador

    Cliente->>View: POST {evento_id, localidad_id}
    View->>Ser: is_valid(data)
    alt datos con formato inválido
        Ser-->>Cliente: 400 Bad Request
    end
    View->>Svc: ejecutar(ReservaBoletaDTO)
    activate Svc
    Svc->>Repo: obtener_por_id(localidad_id)
    alt localidad no existe
        Repo-->>Svc: RecursoNoEncontradoError
        Svc-->>View: RecursoNoEncontradoError
        View-->>Cliente: 404 Not Found
    end
    Repo-->>Svc: Localidad (bloqueada con select_for_update)

    Svc->>Bld: para_usuario().para_evento().en_localidad(localidad)
    alt localidad sin cupo
        Bld-->>Svc: SinCupoError
        Svc-->>View: SinCupoError (ConflictoEstadoError)
        View-->>Cliente: 409 Conflict
    end
    Svc->>Bld: generar_codigo_qr().marcar_reservada_ahora().build()
    Bld-->>Svc: BoletaData (válido y consistente)

    Svc->>ORM: guardar(BoletaData)
    ORM-->>Svc: Boleta (persistida)
    Svc->>Repo: localidad.vendidas += 1; save()

    Svc->>Fac: crear()
    Fac-->>Svc: NotificadorBase (según ENV_TYPE)
    Svc->>Not: enviar_confirmacion_boleta(boleta)

    deactivate Svc
    Svc-->>View: Boleta
    View-->>Cliente: 201 Created + BoletaSerializer(boleta)
```

## Puntos clave del flujo

1. **Un único punto de fallo por causa** — cada excepción de dominio
   (`RecursoNoEncontradoError`, `SinCupoError` → `ConflictoEstadoError`)
   se lanza en la capa donde se detecta y se traduce a HTTP en un único
   lugar: `_respuesta_error_dominio()` en `interfaces/api/views.py`.
2. **Atomicidad** — todo el método `ReservaBoletaService.ejecutar()`
   está envuelto en `@transaction.atomic`: si la notificación fallara,
   la boleta y el descuento de cupo se revertirían.
3. **Bloqueo de fila** — `LocalidadRepository.obtener_por_id()` usa
   `select_for_update()` para evitar que dos reservas concurrentes sobre
   la última unidad de cupo terminen ambas en `201`.
4. **El Builder es la única puerta de entrada a `Boleta`** — ni el
   Service ni la Vista arman un `Boleta(...)` a mano; siempre pasa por
   `BoletaBuilder`, que es quien decide si el estado es consistente.
