# Microservicio de QR (Flask) — imagen independiente del monolito Django.
FROM python:3.11-slim

# Buenas prácticas: no generar .pyc y no bufferizar logs.
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

WORKDIR /app

# Instalar dependencias primero para aprovechar la cache de capas de Docker.
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copiar el código del servicio.
COPY . .

# Usuario no-root por seguridad.
RUN useradd --create-home appuser
USER appuser

EXPOSE 5000

# Gunicorn como servidor WSGI de producción (2 workers, timeout amplio para
# la generación de imágenes QR pesadas). `app:app` = módulo app.py, objeto app.
CMD ["gunicorn", "--bind", "0.0.0.0:5000", "--workers", "2", "--timeout", "60", "app:app"]
