# 4. Patrones creacionales: Builder y Factory

Esta sección parte del trabajo previo del taller (`Implementacion-Patron-Creacional.md`)
y lo actualiza a la estructura final del proyecto.

## Builder — `BoletaBuilder` (`domain/builders/boleta_builder.py`)

### Problema

Crear una boleta implica varios pasos condicionales que deben ejecutarse
en orden antes de considerar el objeto válido: verificar que la
localidad tenga cupo, tomar el precio vigente de esa localidad, generar
el código QR y marcar la hora de reserva. Si esto se hiciera con
`Boleta.objects.create(...)` directo desde la vista o el service, sería
fácil olvidar una validación o dejar el objeto a medias.

### Solución

`BoletaBuilder` expone una interfaz fluida
(`.para_usuario().para_evento().en_localidad().generar_codigo_qr().build()`)
y garantiza que `build()` nunca entregue un `BoletaData` inconsistente:
o lanza `BoletaInvalidaError` / `SinCupoError`, o entrega un objeto
completo. Es la **única** puerta de entrada para construir una boleta en
todo el sistema.

### Por qué Builder y no otro patrón

Se descartó un simple método de fábrica (`Boleta.crear(...)`) porque los
pasos son condicionales y algunos dependen del resultado de otros (el
precio depende de la localidad; el QR es independiente). Builder permite
expresar ese orden explícitamente y reutilizar el mismo objeto
`BoletaData` como resultado intermedio testeable.

## Factory — `NotificadorFactory` (`infra/factories/notificador_factory.py`)

### Problema

El sistema necesita notificar al usuario cuando su boleta se reserva,
pero **qué** implementación de notificación usar depende del ambiente:
en desarrollo/tests no queremos enviar correos reales; en producción sí.

### Solución

`NotificadorFactory.crear()` decide, según la variable de entorno
`ENV_TYPE` (`MOCK` por defecto, `REAL` en producción), si instanciar
`ConsolaNotificador` o `EmailNotificador`. Ambas implementan
`NotificadorBase` (Dependency Inversion Principle): `ReservaBoletaService`
solo depende de esa interfaz, nunca pregunta `if env == "MOCK"`.

### Por qué Factory

Es exactamente el caso de uso que motiva este patrón: gestionar una
**dependencia externa que varía según configuración**, sin dispersar
lógica condicional por el código. Cuando en la Entrega 2 se añada
`Pago`, se replicará el mismo patrón con una `PasarelaPagoFactory`.

## Snippet clave (Service Layer usando ambos patrones)

```python
# application/services.py — ReservaBoletaService.ejecutar()
localidad = self._localidad_repo.obtener_por_id(datos.localidad_id)

boleta_data = (
    BoletaBuilder()
    .para_usuario(datos.usuario_id)
    .para_evento(datos.evento_id)
    .en_localidad(localidad)      # <- valida cupo, toma precio (SinCupoError si no hay)
    .generar_codigo_qr()
    .marcar_reservada_ahora()
    .build()
)

boleta = self._boleta_repo.guardar(boleta_data)
localidad.vendidas += 1
localidad.save(update_fields=["vendidas"])

self._notificador.enviar_confirmacion_boleta(boleta)   # <- instancia resuelta por Factory
```

## Diferencia respecto a la versión del taller

- Las excepciones (`BoletaInvalidaError`, `SinCupoError`) ahora heredan
  de una jerarquía común en `domain/exceptions.py`, para que la capa de
  presentación las traduzca a HTTP de forma uniforme (ver
  [API Gateway](03-API-Gateway.md)).
- `ReservaBoletaService` ahora corre dentro de `@transaction.atomic` y
  usa `select_for_update()` en `LocalidadRepository`, para evitar
  condiciones de carrera al descontar el último cupo disponible.
- Se agregaron `CancelarBoletaService`, `CrearEventoService` y
  `PublicarEventoService` siguiendo el mismo estilo (repos inyectables,
  una responsabilidad por clase).
