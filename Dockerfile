# Monolito Django (ZonaVip) — imagen del servicio legacy.
FROM python:3.11-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

WORKDIR /app

# gettext es necesario para compilar los catálogos i18n (compilemessages).
RUN apt-get update \
    && apt-get install -y --no-install-recommends gettext \
    && rm -rf /var/lib/apt/lists/*

# Dependencias de Python (incluye gunicorn como WSGI de producción).
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt gunicorn>=21.2

# Código del monolito.
COPY . .

# Compila los catálogos de traducción (.po -> .mo) y recolecta estáticos.
RUN python manage.py compilemessages \
    && python manage.py collectstatic --noinput

# Usuario no-root.
RUN useradd --create-home appuser && chown -R appuser /app
USER appuser

EXPOSE 8000

# Migra la BD y arranca Gunicorn. config.wsgi:application es el entrypoint WSGI.
CMD ["sh", "-c", "python manage.py migrate --noinput && gunicorn --bind 0.0.0.0:8000 --workers 3 config.wsgi:application"]
