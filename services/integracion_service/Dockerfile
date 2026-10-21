# Microservicio de Integración (Flask) — imagen independiente.
FROM python:3.11-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

RUN useradd --create-home appuser
USER appuser

EXPOSE 5001

# Gunicorn como WSGI de producción. El servicio hace llamadas HTTP salientes,
# por eso un timeout algo mayor.
CMD ["gunicorn", "--bind", "0.0.0.0:5001", "--workers", "2", "--timeout", "30", "app:app"]
