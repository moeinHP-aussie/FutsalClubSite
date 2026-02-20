# futsal_config/__init__.py
# ✅ بارگذاری Celery هنگام راه‌اندازی Django — برای periodic tasks ضروری است
from .celery import app as celery_app

__all__ = ("celery_app",)