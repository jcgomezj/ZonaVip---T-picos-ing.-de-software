# Monolito Django (ZonaVip) — imagen del servicio legacy.
FROM python:3.11-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

WORKDIR /app

# Dependencias del sistema mínimas + gunicorn como WSGI de producción.
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt gunicorn>=21.2

# Código del monolito.
COPY . .

# Usuario no-root.
RUN useradd --create-home appuser && chown -R appuser /app
USER appuser

EXPOSE 8000

# Migra y arranca Gunicorn. config.wsgi:application es el punto de entrada WSGI.
CMD ["sh", "-c", "python manage.py migrate --noinput && gunicorn --bind 0.0.0.0:8000 --workers 3 config.wsgi:application"]
