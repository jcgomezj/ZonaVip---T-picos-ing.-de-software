# Microservicio de QR — ZonaVip

Servicio ligero en **Flask** que expone, vía API REST/JSON, la generación y
validación de códigos QR de boletas. Es el módulo **estrangulado** del
monolito Django siguiendo el *Strangler Pattern* (Taller 02).

> Documentación arquitectónica completa y matriz de decisión:
> [`docs/wiki/05-Migracion-a-Microservicios.md`](../../docs/wiki/05-Migracion-a-Microservicios.md)

## ¿Por qué se estranguló este módulo?

La generación de códigos QR es **CPU-intensiva** (renderizado de la matriz
QR + codificación PNG) y de **bajo acoplamiento** con la base de datos del
monolito: solo necesita `boleta_id` y `codigo_qr`, no el resto del ORM. Al
aislarla, el render de imágenes deja de bloquear el hilo principal de Django.

## API

Todas las respuestas son `application/json`. Detrás de Nginx, el prefijo
público es `/api/v2/qr/`.

| Método | Ruta | Descripción |
|---|---|---|
| `GET`  | `/api/v2/qr/health`  | Health check del servicio |
| `POST` | `/api/v2/qr/generar` | Genera un QR (PNG en base64) para una boleta |
| `POST` | `/api/v2/qr/validar` | Valida la firma HMAC de un payload de QR |

### Generar

```bash
curl -X POST http://localhost/api/v2/qr/generar \
  -H "Content-Type: application/json" \
  -d '{"boleta_id": 1, "codigo_qr": "a1b2c3"}'
```

```json
{
  "boleta_id": 1,
  "codigo_qr": "a1b2c3",
  "payload": "ZONAVIP|1|a1b2c3|9f0a...",
  "imagen_base64": "data:image/png;base64,iVBOR...",
  "formato": "PNG",
  "generado_en_ms": 4.12
}
```

### Validar

```bash
curl -X POST http://localhost/api/v2/qr/validar \
  -H "Content-Type: application/json" \
  -d '{"payload": "ZONAVIP|1|a1b2c3|9f0a..."}'
```

### Contrato de errores (resiliencia)

| Código | Situación |
|---|---|
| `400` | Body no-JSON, `boleta_id` ausente/no numérico, payload vacío |
| `404` | Ruta inexistente |
| `405` | Método HTTP no permitido |
| `500` | Error interno no controlado (respuesta JSON, nunca stacktrace crudo) |

## Ejecutar en local (sin Docker)

```bash
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
python app.py           # http://localhost:5000/api/v2/qr/health
```

## Tests

```bash
pip install -r requirements.txt pytest
pytest
```

10 pruebas: dominio puro (`qr_engine`) + contrato HTTP/JSON de la API.

## Variables de entorno

| Variable | Default | Descripción |
|---|---|---|
| `QR_SECRET` | `zonavip-qr-dev-secret` | Clave HMAC para firmar los QR |
