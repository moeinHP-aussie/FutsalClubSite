"""
futsal_config/wsgi.py
WSGI config — used by Gunicorn in production.
"""
import os
from django.core.wsgi import get_wsgi_application

# ✅ از env var خونده می‌شه — اگه ست نشده بود، development پیش‌فرض باشه
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "futsal_config.settings.development")
application = get_wsgi_application()