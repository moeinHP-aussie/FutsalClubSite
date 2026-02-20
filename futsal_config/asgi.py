"""
futsal_config/asgi.py
ASGI config — for async support / Uvicorn.
"""
import os
from django.core.asgi import get_asgi_application

# ✅ از env var خونده می‌شه — اگه ست نشده بود، development پیش‌فرض باشه
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "futsal_config.settings.development")
application = get_asgi_application()