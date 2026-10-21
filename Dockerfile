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

# Compila los catálogos de traducción (.po -> .mo) y asegura directorios de estáticos y media.
RUN mkdir -p /app/staticfiles /app/media \
    && python manage.py compilemessages \
    && python manage.py collectstatic --noinput

# Usuario no-root con permisos sobre el árbol de la aplicación.
RUN useradd --create-home appuser && chown -R appuser:appuser /app
USER appuser

EXPOSE 8000

# Entrypoint en producción: recolecta estáticos al volumen compartido, corre migraciones y arranca Gunicorn con logs a stdout/stderr.
CMD ["sh", "-c", "python manage.py collectstatic --noinput && python manage.py migrate --noinput && gunicorn --bind 0.0.0.0:8000 --workers 3 --access-logfile - --error-logfile - config.wsgi:application"]
