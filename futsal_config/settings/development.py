"""
futsal_config/settings/development.py
─────────────────────────────────────────────────────────────────────
تنظیمات محیط توسعه و تست Docker
"""
from .base import *  # noqa: F401, F403

DEBUG = True

ALLOWED_HOSTS = ["*"]   # در توسعه همه host ها مجاز

# ── SQLite for local dev (no Postgres needed) ──────────────────────────
# If DOCKER=True, use Postgres instead
import os
if os.environ.get("DATABASE_URL"):
    import dj_database_url
    DATABASES = {"default": dj_database_url.config(conn_max_age=600)}

# ── Email: print to console ───────────────────────────────────────────
EMAIL_BACKEND = "django.core.mail.backends.console.EmailBackend"

# ── Debug Toolbar (optional — install separately) ─────────────────────
# INSTALLED_APPS += ["debug_toolbar"]
# MIDDLEWARE.insert(1, "debug_toolbar.middleware.DebugToolbarMiddleware")
# INTERNAL_IPS = ["127.0.0.1"]

# ── Static files served by Django in dev ──────────────────────────────
STATICFILES_STORAGE = "django.contrib.staticfiles.storage.StaticFilesStorage"

# ── Logging: show everything in development ───────────────────────────
LOGGING["root"]["level"] = "DEBUG"  # noqa: F405
