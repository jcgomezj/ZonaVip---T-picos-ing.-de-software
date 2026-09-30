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
]

MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
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
        "DIRS": [],
        "APP_DIRS": True,
        "OPTIONS": {
            "context_processors": [
                "django.template.context_processors.debug",
                "django.template.context_processors.request",
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

LANGUAGE_CODE = "es-co"
TIME_ZONE = "America/Bogota"
USE_I18N = True
USE_TZ = True

STATIC_URL = "static/"

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
