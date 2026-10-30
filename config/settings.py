import os
from pathlib import Path
from datetime import timedelta

import dj_database_url
from dotenv import load_dotenv

BASE_DIR = Path(__file__).resolve().parent.parent
load_dotenv(BASE_DIR / ".env")


def env_list(name, default=""):
    return [v.strip() for v in os.getenv(name, default).split(",") if v.strip()]


def merge(*lists):
    """Ro'yxatlarni birlashtiradi, takrorlarni olib tashlaydi (tartib saqlanadi)."""
    out = []
    for lst in lists:
        for item in lst:
            if item not in out:
                out.append(item)
    return out


# ---------- Asosiy ----------
SECRET_KEY = os.getenv("SECRET_KEY", "dev-only-insecure-key")
DEBUG = os.getenv("DEBUG", "False") == "True"

ALLOWED_HOSTS = ["localhost", "127.0.0.1", "school-backend-lecj.onrender.com"]
_render_host = os.getenv("RENDER_EXTERNAL_HOSTNAME")
if _render_host and _render_host not in ALLOWED_HOSTS:
    ALLOWED_HOSTS.append(_render_host)

if not DEBUG and SECRET_KEY == "dev-only-insecure-key":
    raise RuntimeError("Productionda SECRET_KEY ni .env / hosting sozlamasiga yozing!")

INSTALLED_APPS = [
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
    # Tashqi
    "rest_framework",
    "corsheaders",
    # Bizning
    "api",
]

MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    "whitenoise.middleware.WhiteNoiseMiddleware",
    "corsheaders.middleware.CorsMiddleware",  # CommonMiddleware dan oldin bo'lishi shart
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
                "django.template.context_processors.request",
                "django.contrib.auth.context_processors.auth",
                "django.contrib.messages.context_processors.messages",
            ],
        },
    },
]

WSGI_APPLICATION = "config.wsgi.application"

# ---------- Foydalanuvchi modeli (birinchi migrate dan OLDIN o'rnatilishi shart) ----------
AUTH_USER_MODEL = "api.User"

# ---------- Baza ----------
# DATABASE_URL bo'lsa PostgreSQL, bo'lmasa lokal SQLite
if os.getenv("DATABASE_URL"):
    DATABASES = {
        "default": dj_database_url.config(conn_max_age=600, ssl_require=not DEBUG)
    }
else:
    DATABASES = {
        "default": {
            "ENGINE": "django.db.backends.sqlite3",
            "NAME": BASE_DIR / "db.sqlite3",
        }
    }

AUTH_PASSWORD_VALIDATORS = [
    {"NAME": "django.contrib.auth.password_validation.MinimumLengthValidator",
     "OPTIONS": {"min_length": 6}},
]

# ---------- Til va vaqt ----------
LANGUAGE_CODE = "uz"
TIME_ZONE = "Asia/Tashkent"
USE_I18N = True
USE_TZ = True

# ---------- Static fayllar ----------
STATIC_URL = "static/"
STATIC_ROOT = BASE_DIR / "staticfiles"
STORAGES = {
    "default": {"BACKEND": "django.core.files.storage.FileSystemStorage"},
    "staticfiles": {"BACKEND": "whitenoise.storage.CompressedStaticFilesStorage"},
}

DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"

# Katta ma'lumotlar (rasm va h.k.) uchun: standart 2.5 MB, endi 15 MB
DATA_UPLOAD_MAX_MEMORY_SIZE = 15 * 1024 * 1024

# ---------- DRF + JWT ----------
REST_FRAMEWORK = {
    "DEFAULT_AUTHENTICATION_CLASSES": (
        "rest_framework_simplejwt.authentication.JWTAuthentication",
    ),
    "DEFAULT_PERMISSION_CLASSES": (
        "rest_framework.permissions.IsAuthenticated",
    ),
    "DEFAULT_THROTTLE_CLASSES": (
        "rest_framework.throttling.AnonRateThrottle",
        "rest_framework.throttling.UserRateThrottle",
    ),
    # Frontend /api/version ni tez-tez so'raydi, shuning uchun limit oshirildi
    "DEFAULT_THROTTLE_RATES": {"anon": "1200/min", "user": "1200/min"},
}

SIMPLE_JWT = {
    "ACCESS_TOKEN_LIFETIME": timedelta(hours=1),
    "REFRESH_TOKEN_LIFETIME": timedelta(days=30),
}

# ---------- Ruxsat etilgan frontend manzillari ----------
FRONTEND_ORIGINS = [
    "http://localhost:5173",
    "http://localhost:3000",
    "https://8class.vercel.app",
    "https://8b.uz",
    "https://www.8b.uz",
    "https://8bclass.uz",
    "https://www.8bclass.uz",
]

CORS_ALLOWED_ORIGINS = merge(FRONTEND_ORIGINS, env_list("CORS_ALLOWED_ORIGINS"))
CSRF_TRUSTED_ORIGINS = merge(
    FRONTEND_ORIGINS,
    ["https://school-backend-lecj.onrender.com"],
    env_list("CSRF_TRUSTED_ORIGINS"),
)

# ---------- Productionda (Render) ----------
SECURE_PROXY_SSL_HEADER = ("HTTP_X_FORWARDED_PROTO", "https")