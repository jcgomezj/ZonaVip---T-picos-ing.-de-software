# Implementación del Patrón Creacional

## Módulo: Reserva de Boletas

### Problema

La creación de una boleta implicaba, todo mezclado en la vista de Django:
validar si la localidad tenía cupo disponible, calcular el precio vigente,
generar el código QR, guardar en base de datos y notificar al usuario por
correo. Esto violaba SRP (la vista hacía demasiado) y dificultaba las
pruebas unitarias, porque no se podía probar la lógica sin levantar
peticiones HTTP reales.

### Solución Arquitectónica

- **Service Layer**: se creó `ReservaBoletaService` (`application/services.py`)
  para orquestar todo el flujo: obtener la localidad, pedirle al Builder que
  construya la boleta, persistirla y notificar. La vista (`ReservarBoletaView`)
  quedó con menos de 15 líneas de lógica.

- **Builder**: `BoletaBuilder` (`domain/builders/boleta_builder.py`) construye
  la boleta paso a paso con Fluent Interface (`.para_usuario().en_localidad()
  .generar_codigo_qr().build()`), garantizando que nunca se persista un objeto
  inválido (por ejemplo, una localidad sin cupo lanza `BoletaInvalidaError`
  *antes* de tocar la base de datos).

- **Factory**: `NotificadorFactory` (`infra/factories/notificador_factory.py`)
  decide si se instancia `EmailNotificador` (real, SendGrid/SMTP) o
  `ConsolaNotificador` (mock para desarrollo/tests), dependiendo de la
  variable de entorno `ENV_TYPE` (`MOCK` por defecto, `REAL` en producción).
  El `Service` nunca pregunta `if env == "MOCK"`; solo depende de la interfaz
  `NotificadorBase` (Dependency Inversion Principle).

### Diagrama de interacción (Vista → Service → Builder/Factory)

```
Cliente HTTP
    |
    v
ReservarBoletaView (interfaces/views.py)
    |  arma ReservaBoletaDTO desde el request
    v
ReservaBoletaService.ejecutar(datos)  (application/services.py)
    |
    |--> LocalidadRepository.obtener_por_id()   (trae la Localidad)
    |
    |--> BoletaBuilder                           (domain/builders/)
    |        .para_usuario()
    |        .para_evento()
    |        .en_localidad()   -> valida cupo, toma precio
    |        .generar_codigo_qr()
    |        .marcar_reservada_ahora()
    |        .build()          -> BoletaData validado
    |
    |--> BoletaRepository.guardar(boleta_data)   (persiste)
    |
    |--> NotificadorFactory.crear()              (infra/factories/)
    |        -> ConsolaNotificador (ENV_TYPE=MOCK)
    |        -> EmailNotificador   (ENV_TYPE=REAL)
    |
    v
JsonResponse(boleta) al cliente
```

### Snippet clave

```python
# application/services.py
def ejecutar(self, datos: ReservaBoletaDTO):
    localidad = self._localidad_repo.obtener_por_id(datos.localidad_id)

    boleta_data = (
        BoletaBuilder()
        .para_usuario(datos.usuario_id)
        .en_localidad(localidad)
        .generar_codigo_qr()
        .marcar_reservada_ahora()
        .build()
    )

    boleta = self._boleta_repo.guardar(boleta_data)
    self._notificador.enviar_confirmacion_boleta(boleta)
    return boleta
```

### Justificación de las decisiones de diseño

- Se eligió **Builder** (y no un simple `Boleta.objects.create(...)`) porque
  la creación de la boleta tiene múltiples pasos condicionales (validar cupo,
  calcular precio, generar QR) que deben ejecutarse en orden y de forma
  atómica antes de considerar el objeto válido.
- Se eligió **Factory** para el notificador porque es una dependencia externa
  (envío de correo) que cambia según el ambiente (dev/test vs. producción),
  y queríamos que ese cambio fuera controlado por configuración
  (`ENV_TYPE`), no por lógica condicional dispersa en el código.
- El **Service Layer** recibe sus repositorios inyectados en el constructor,
  lo que permite reemplazarlos por mocks en los tests unitarios sin
  necesidad de una base de datos real.
