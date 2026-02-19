"""
futsal_config/settings/base.py
─────────────────────────────────────────────────────────────────────
تنظیمات مشترک برای تمام محیط‌ها (dev / production)
"""
import os
from pathlib import Path

# ── Paths ─────────────────────────────────────────────────────────────
# BASE_DIR = .../futsal_club_project/
BASE_DIR = Path(__file__).resolve().parent.parent.parent

SECRET_KEY = os.environ.get("SECRET_KEY", "django-insecure-change-this-in-production")
DEBUG      = os.environ.get("DEBUG", "False") == "True"

ALLOWED_HOSTS = os.environ.get("ALLOWED_HOSTS", "localhost,127.0.0.1").split(",")


# ── Application Definition ────────────────────────────────────────────
INSTALLED_APPS = [
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
    # Third-party
    "django_jalali",
    "django_celery_beat",
    "django_celery_results",
    # Our app — must use FutsalClubConfig to register signals
    "futsal_club.apps.FutsalClubConfig",
]

MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    "whitenoise.middleware.WhiteNoiseMiddleware",   # static files in production
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
]

ROOT_URLCONF = "futsal_config.urls"

# ── Templates ─────────────────────────────────────────────────────────
# ⚠️  templates/ folder is at PROJECT ROOT — NOT inside futsal_club/
TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        "DIRS":    [BASE_DIR / "templates"],          # ← کلیدی
        "APP_DIRS": True,
        "OPTIONS": {
            "context_processors": [
                "django.template.context_processors.debug",
                "django.template.context_processors.request",
                "django.contrib.auth.context_processors.auth",
                "django.contrib.messages.context_processors.messages",
                # اعلان‌های خوانده‌نشده را به همه templates تزریق می‌کند
                "futsal_club.context_processors.global_context",
            ],
        },
    },
]

WSGI_APPLICATION = "futsal_config.wsgi.application"


# ── Database ──────────────────────────────────────────────────────────
# Development uses SQLite; Production overrides this via DATABASE_URL
DATABASES = {
    "default": {
        "ENGINE":  "django.db.backends.sqlite3",
        "NAME":    BASE_DIR / "db.sqlite3",
    }
}


# ── Auth ──────────────────────────────────────────────────────────────
AUTH_USER_MODEL = "futsal_club.CustomUser"

AUTH_PASSWORD_VALIDATORS = [
    {"NAME": "django.contrib.auth.password_validation.UserAttributeSimilarityValidator"},
    {"NAME": "django.contrib.auth.password_validation.MinimumLengthValidator"},
    {"NAME": "django.contrib.auth.password_validation.CommonPasswordValidator"},
    {"NAME": "django.contrib.auth.password_validation.NumericPasswordValidator"},
]

LOGIN_URL          = "/auth/login/"
LOGIN_REDIRECT_URL = "/dashboard/"
LOGOUT_REDIRECT_URL = "/auth/login/"


# ── Internationalization ──────────────────────────────────────────────
LANGUAGE_CODE = "fa"
TIME_ZONE     = "Asia/Tehran"
USE_I18N      = True
USE_TZ        = True

LOCALE_PATHS = [BASE_DIR / "locale"]


# ── Static & Media ────────────────────────────────────────────────────
# ⚠️  static/ folder is at PROJECT ROOT
STATIC_URL       = "/static/"
STATICFILES_DIRS = [BASE_DIR / "static"]           # ← source
STATIC_ROOT      = BASE_DIR / "staticfiles"        # ← collectstatic output (gitignored)

MEDIA_URL  = "/media/"
MEDIA_ROOT = BASE_DIR / "mediafiles"               # ← uploads (gitignored)

STATICFILES_STORAGE = "whitenoise.storage.CompressedManifestStaticFilesStorage"


# ── Default PK ────────────────────────────────────────────────────────
DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"


# ── Celery ────────────────────────────────────────────────────────────
CELERY_BROKER_URL         = os.environ.get("REDIS_URL", "redis://localhost:6379/0")
CELERY_RESULT_BACKEND     = os.environ.get("REDIS_URL", "redis://localhost:6379/0")
CELERY_BEAT_SCHEDULER     = "django_celery_beat.schedulers:DatabaseScheduler"
CELERY_TIMEZONE           = "Asia/Tehran"
CELERY_TASK_SERIALIZER    = "json"
CELERY_RESULT_SERIALIZER  = "json"
CELERY_ACCEPT_CONTENT     = ["json"]


# ── Cache (Redis) ─────────────────────────────────────────────────────
CACHES = {
    "default": {
        "BACKEND":  "django.core.cache.backends.redis.RedisCache",
        "LOCATION": os.environ.get("REDIS_URL", "redis://localhost:6379/1"),
    }
}


# ── Session ───────────────────────────────────────────────────────────
SESSION_ENGINE         = "django.contrib.sessions.backends.cache"
SESSION_CACHE_ALIAS    = "default"
SESSION_COOKIE_AGE     = 86400 * 7   # 7 days


# ── File Upload ───────────────────────────────────────────────────────
DATA_UPLOAD_MAX_MEMORY_SIZE = 209715200  # 200 MB
FILE_UPLOAD_MAX_MEMORY_SIZE = 209715200


# ── Zarinpal ──────────────────────────────────────────────────────────
ZARINPAL_MERCHANT_ID = os.environ.get("ZARINPAL_MERCHANT_ID", "")
ZARINPAL_SANDBOX     = os.environ.get("ZARINPAL_SANDBOX", "True") == "True"


# ── Logging ───────────────────────────────────────────────────────────
LOGGING = {
    "version": 1,
    "disable_existing_loggers": False,
    "formatters": {
        "verbose": {"format": "{levelname} {asctime} {module} {message}", "style": "{"},
        "simple":  {"format": "{levelname} {message}", "style": "{"},
    },
    "handlers": {
        "console": {"class": "logging.StreamHandler", "formatter": "simple"},
        "file":    {
            "class":     "logging.handlers.RotatingFileHandler",
            "filename":  BASE_DIR / "logs" / "django.log",
            "maxBytes":  1024 * 1024 * 10,  # 10 MB
            "backupCount": 5,
            "formatter": "verbose",
        },
    },
    "root": {"handlers": ["console"], "level": "INFO"},
    "loggers": {
        "django":      {"handlers": ["console", "file"], "level": "WARNING", "propagate": False},
        "futsal_club": {"handlers": ["console", "file"], "level": "INFO",    "propagate": False},
    },
}
