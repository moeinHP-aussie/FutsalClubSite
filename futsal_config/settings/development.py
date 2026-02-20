"""
futsal_config/settings/development.py
─────────────────────────────────────────────────────────────────────
تنظیمات محیط توسعه و تست Docker
"""
from .base import *  # noqa: F401, F403

DEBUG = True

ALLOWED_HOSTS = ["*"]   # در توسعه همه host ها مجاز

# ── Database ──────────────────────────────────────────────────────────
import os
if os.environ.get("DATABASE_URL"):
    import dj_database_url
    DATABASES = {"default": dj_database_url.config(conn_max_age=600)}
# اگر DATABASE_URL ست نشده، از SQLite در base.py استفاده می‌شه

# ── Session: از DB استفاده کن نه Redis ────────────────────────────────
# ✅ در dev ممکنه Redis نباشه — از db-backed session استفاده می‌کنیم
SESSION_ENGINE = "django.contrib.sessions.backends.db"

# ── Cache: memory-based در development ───────────────────────────────
# ✅ اگر Redis نداریم، cache رو از حافظه بخونیم
CACHES = {
    "default": {
        "BACKEND": "django.core.cache.backends.locmem.LocMemCache",
    }
}

# ── Email: print to console ───────────────────────────────────────────
EMAIL_BACKEND = "django.core.mail.backends.console.EmailBackend"

# ── Static files served by Django in dev ──────────────────────────────
STATICFILES_STORAGE = "django.contrib.staticfiles.storage.StaticFilesStorage"

# ── Logging: show everything in development ───────────────────────────
LOGGING["root"]["level"] = "DEBUG"  # noqa: F405