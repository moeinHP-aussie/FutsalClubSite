"""
futsal_config/asgi.py
ASGI config — for async support / Uvicorn.
"""
import os
from django.core.asgi import get_asgi_application

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "futsal_config.settings.production")
application = get_asgi_application()
