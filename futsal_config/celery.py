"""
futsal_config/celery.py
─────────────────────────────────────────────────────────────────────
Celery application configuration + beat schedule
"""
import os

from celery import Celery
from celery.schedules import crontab

# ✅ از env var خونده می‌شه — اگه ست نشده بود، development پیش‌فرض باشه
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "futsal_config.settings.development")

app = Celery("futsal_club")

# Read config from Django settings (CELERY_* keys)
app.config_from_object("django.conf:settings", namespace="CELERY")

# Auto-discover tasks in all INSTALLED_APPS
app.autodiscover_tasks()


# ── Periodic Task Schedule ────────────────────────────────────────────
app.conf.beat_schedule = {
    # بررسی روزانه بیمه‌های در حال انقضا — هر روز ساعت ۸ صبح
    "check-insurance-expiry-daily": {
        "task":     "futsal_club.tasks.check_insurance_expiry_task",
        "schedule": crontab(hour=8, minute=0),
    },
    # بدهکارسازی فاکتورهای سررسیده — اول هر ماه
    "mark-overdue-invoices-monthly": {
        "task":     "futsal_club.tasks.mark_overdue_invoices_task",
        "schedule": crontab(day_of_month=1, hour=6, minute=0),
    },
    # پاک‌سازی فایل‌های import موقت — هر شب
    "cleanup-temp-imports-nightly": {
        "task":     "futsal_club.tasks.cleanup_temp_imports_task",
        "schedule": crontab(hour=2, minute=0),
    },
}

app.conf.timezone = "Asia/Tehran"