"""
futsal_config/settings/production.py
─────────────────────────────────────────────────────────────────────
تنظیمات محیط تولید (Docker + Gunicorn + Postgres)
"""
from .base import *  # noqa: F401, F403
import os

DEBUG = False

# ── Database: PostgreSQL ──────────────────────────────────────────────
import dj_database_url  # pip install dj-database-url
DATABASES = {
    "default": dj_database_url.config(
        default=os.environ.get("DATABASE_URL", "postgres://futsal:futsal123@postgres:5432/futsal_db"),
        conn_max_age=600,
        ssl_require=False,   # True if using SSL in production
    )
}

# ── Security ──────────────────────────────────────────────────────────
SECURE_BROWSER_XSS_FILTER      = True
SECURE_CONTENT_TYPE_NOSNIFF    = True
X_FRAME_OPTIONS                 = "SAMEORIGIN"
# For HTTPS only (enable when SSL is configured):
# SECURE_SSL_REDIRECT            = True
# SESSION_COOKIE_SECURE          = True
# CSRF_COOKIE_SECURE             = True
# SECURE_HSTS_SECONDS            = 31536000

# ── Static: WhiteNoise ────────────────────────────────────────────────
STATICFILES_STORAGE = "whitenoise.storage.CompressedManifestStaticFilesStorage"

# ── Sentry Error Tracking (optional) ─────────────────────────────────
SENTRY_DSN = os.environ.get("SENTRY_DSN", "")
if SENTRY_DSN:
    import sentry_sdk
    from sentry_sdk.integrations.django import DjangoIntegration
    sentry_sdk.init(
        dsn=SENTRY_DSN,
        integrations=[DjangoIntegration()],
        traces_sample_rate=0.2,
        send_default_pii=False,
    )
