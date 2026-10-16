"""
Django settings para ZonaVip.

Nota de arquitectura: `INSTALLED_APPS` solo registra las apps de Django
(persistencia). Las capas `domain/`, `application/` e `interfaces/` son
paquetes Python normales, deliberadamente por fuera de `apps/`, para dejar
explícito que el dominio y los servicios no dependen del framework más
de lo estrictamente necesario. Ver docs/wiki/01-Estructura-de-Carpetas.md.
"""

import os
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent

SECRET_KEY = os.environ.get(
    "DJANGO_SECRET_KEY", "clave-de-desarrollo-cambiar-en-produccion"
)

DEBUG = os.environ.get("DJANGO_DEBUG", "True").lower() in ("1", "true", "yes")

ALLOWED_HOSTS = os.environ.get("DJANGO_ALLOWED_HOSTS", "*").split(",")

INSTALLED_APPS = [
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
    "rest_framework",
    "apps.usuarios",
    "apps.eventos",
    "apps.boletas",
    "apps.reportes",
    "interfaces.web",
]

MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    # WhiteNoise sirve estáticos en producción (debe ir justo tras Security).
    "whitenoise.middleware.WhiteNoiseMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    # LocaleMiddleware habilita la selección de idioma por sesión/cookie/
    # cabecera Accept-Language (i18n). Debe ir DESPUÉS de SessionMiddleware
    # y ANTES de CommonMiddleware.
    "django.middleware.locale.LocaleMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
]

ROOT_URLCONF = "config.urls"

TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        "DIRS": [BASE_DIR / "interfaces" / "web" / "templates"],
        "APP_DIRS": True,
        "OPTIONS": {
            "context_processors": [
                "django.template.context_processors.debug",
                "django.template.context_processors.request",
                "django.template.context_processors.i18n",
                "django.contrib.auth.context_processors.auth",
                "django.contrib.messages.context_processors.messages",
            ],
        },
    },
]

WSGI_APPLICATION = "config.wsgi.application"

# Motor de persistencia configurable por entorno: SQLite en local (por
# defecto) y PostgreSQL cuando se despliega con Docker Compose (se define
# DJANGO_DB_ENGINE=django.db.backends.postgresql). El resto de las capas no
# se entera: el ORM queda detrás de los Repositorios en application/services.py.
_DB_ENGINE = os.environ.get("DJANGO_DB_ENGINE", "django.db.backends.sqlite3")

if _DB_ENGINE == "django.db.backends.sqlite3":
    DATABASES = {
        "default": {
            "ENGINE": _DB_ENGINE,
            "NAME": BASE_DIR / "db.sqlite3",
        }
    }
else:
    DATABASES = {
        "default": {
            "ENGINE": _DB_ENGINE,
            "NAME": os.environ.get("DJANGO_DB_NAME", "zonavip"),
            "USER": os.environ.get("DJANGO_DB_USER", "zonavip"),
            "PASSWORD": os.environ.get("DJANGO_DB_PASSWORD", "zonavip"),
            "HOST": os.environ.get("DJANGO_DB_HOST", "db"),
            "PORT": os.environ.get("DJANGO_DB_PORT", "5432"),
        }
    }

AUTH_USER_MODEL = "usuarios.Usuario"

AUTH_PASSWORD_VALIDATORS = [
    {"NAME": "django.contrib.auth.password_validation.UserAttributeSimilarityValidator"},
    {"NAME": "django.contrib.auth.password_validation.MinimumLengthValidator"},
    {"NAME": "django.contrib.auth.password_validation.CommonPasswordValidator"},
    {"NAME": "django.contrib.auth.password_validation.NumericPasswordValidator"},
]

# ---------------------------------------------------------------------------
# Internacionalización (i18n) — Entrega 2
#
# Soporte bilingüe completo ES/EN mediante gettext. Todos los textos de la UI
# se marcan con {% trans %} / gettext() y se traducen en los catálogos .po;
# NO hay textos quemados en un solo idioma.
# ---------------------------------------------------------------------------
LANGUAGE_CODE = "es"
TIME_ZONE = "America/Bogota"
USE_I18N = True
USE_TZ = True

LANGUAGES = [
    ("es", "Español"),
    ("en", "English"),
]

# Carpeta donde viven los catálogos de traducción (.po / .mo).
LOCALE_PATHS = [BASE_DIR / "locale"]

# ---------------------------------------------------------------------------
# Archivos estáticos
# ---------------------------------------------------------------------------
STATIC_URL = "static/"
STATICFILES_DIRS = [BASE_DIR / "interfaces" / "web" / "static"]
STATIC_ROOT = BASE_DIR / "staticfiles"
# Almacenamiento comprimido + con hash de WhiteNoise para cache-busting.
STORAGES = {
    "default": {"BACKEND": "django.core.files.storage.FileSystemStorage"},
    "staticfiles": {
        "BACKEND": "whitenoise.storage.CompressedManifestStaticFilesStorage"
    },
}

DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"

REST_FRAMEWORK = {
    "DEFAULT_AUTHENTICATION_CLASSES": [
        "rest_framework.authentication.SessionAuthentication",
        "rest_framework.authentication.BasicAuthentication",
    ],
    "DEFAULT_PERMISSION_CLASSES": [
        "rest_framework.permissions.AllowAny",
    ],
}

# ---------------------------------------------------------------------------
# Celery + Redis — Comunicación asíncrona (Entrega 2)
#
# El Message Broker (Redis) desacopla procesos de fondo (reportes,
# notificaciones) del ciclo request/response de Django. La URL se inyecta por
# entorno: en Docker apunta al servicio `redis`, en local a localhost.
# ---------------------------------------------------------------------------
CELERY_BROKER_URL = os.environ.get("CELERY_BROKER_URL", "redis://localhost:6379/0")
CELERY_RESULT_BACKEND = os.environ.get("CELERY_RESULT_BACKEND", "redis://localhost:6379/1")
CELERY_TASK_SERIALIZER = "json"
CELERY_RESULT_SERIALIZER = "json"
CELERY_ACCEPT_CONTENT = ["json"]
CELERY_TIMEZONE = TIME_ZONE

# URL base del microservicio de integración (para enriquecer vistas del front).
INTEGRACION_SERVICE_URL = os.environ.get(
    "INTEGRACION_SERVICE_URL", "http://localhost:5001"
)

# ---------------------------------------------------------------------------
# Autenticación del frontend (zona privada del panel del sistema).
# ---------------------------------------------------------------------------
LOGIN_URL = "web:login"
LOGIN_REDIRECT_URL = "web:panel"
LOGOUT_REDIRECT_URL = "web:home"
