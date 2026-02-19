"""
futsal_config/wsgi.py
WSGI config — used by Gunicorn in production.
"""
import os
from django.core.wsgi import get_wsgi_application

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "futsal_config.settings.production")
application = get_wsgi_application()
