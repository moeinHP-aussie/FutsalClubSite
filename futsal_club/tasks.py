"""
tasks.py
─────────────────────────────────────────────────────────────────────
تسک‌های پس‌زمینه Celery
1. صدور فاکتور ماهانه (اول هر ماه)
2. بررسی روزانه بیمه‌های در حال انقضا
3. علامت‌گذاری بدهکاران (پانزدهم هر ماه)

celery beat schedule (settings.py):
    CELERY_BEAT_SCHEDULE = {
        'monthly-invoice-generation': {
            'task': 'futsal.tasks.generate_monthly_invoices_task',
            'schedule': crontab(hour=6, minute=0, day_of_month=1),
        },
        'daily-insurance-check': {
            'task': 'futsal.tasks.check_insurance_expiry_task',
            'schedule': crontab(hour=7, minute=0),
        },
        'mark-debtors': {
            'task': 'futsal.tasks.mark_debtors_task',
            'schedule': crontab(hour=8, minute=0, day_of_month=15),
        },
    }
"""

from __future__ import annotations

import logging

from celery import shared_task

logger = logging.getLogger(__name__)


@shared_task(bind=True, max_retries=3, default_retry_delay=300)
def generate_monthly_invoices_task(self):
    """
    صدور فاکتور ماهانه برای تمام دسته‌های فعال.
    هر ماه یکم اجرا می‌شود.
    تسک idempotent است — اجرای دوباره آن بدون عوارض جانبی است.
    """
    from .services.payroll_service import PayrollService
    from .utils.jalali_utils import JalaliMonth

    try:
        month   = JalaliMonth.current()
        results = PayrollService.generate_invoices_all_categories(jalali_month=month)

        total_created = sum(b.created_count for b in results.values())
        total_skipped = sum(b.skipped_count for b in results.values())
        total_errors  = sum(b.error_count   for b in results.values())

        logger.info(
            "[صدور فاکتور %s] ایجاد: %d  |  رد شده: %d  |  خطا: %d",
            month, total_created, total_skipped, total_errors,
        )

        return {
            "month":   str(month),
            "created": total_created,
            "skipped": total_skipped,
            "errors":  total_errors,
        }

    except Exception as exc:
        logger.exception("خطا در تسک صدور فاکتور ماهانه: %s", exc)
        raise self.retry(exc=exc)


@shared_task(bind=True, max_retries=3, default_retry_delay=60)
def check_insurance_expiry_task(self):
    """
    بررسی روزانه بیمه‌های در حال انقضا.
    اعلان به بازیکن، مربی و مدیر فنی.
    """
    from .services.payroll_service import PayrollService

    try:
        count = PayrollService.send_insurance_expiry_notifications(days_ahead=30)
        logger.info("[بررسی بیمه] %d اعلان ارسال شد.", count)
        return {"notifications_sent": count}

    except Exception as exc:
        logger.exception("خطا در تسک بررسی بیمه: %s", exc)
        raise self.retry(exc=exc)


@shared_task(bind=True, max_retries=2)
def mark_debtors_task(self):
    """
    فاکتورهای پرداخت‌نشده‌ی ماه قبل را به وضعیت 'بدهکار' تغییر می‌دهد.
    پانزدهم هر ماه اجرا می‌شود.
    """
    from .models import PlayerInvoice
    from .utils.jalali_utils import JalaliMonth

    try:
        prev_month = JalaliMonth.current().prev_month

        updated = PlayerInvoice.objects.filter(
            jalali_year=prev_month.year,
            jalali_month=prev_month.month,
            status=PlayerInvoice.PaymentStatus.PENDING,
        ).update(status=PlayerInvoice.PaymentStatus.DEBTOR)

        logger.info(
            "[علامت‌گذاری بدهکار] %d فاکتور ماه %s به بدهکار تغییر یافت.",
            updated, prev_month,
        )
        return {"updated": updated, "month": str(prev_month)}

    except Exception as exc:
        logger.exception("خطا در تسک علامت‌گذاری بدهکاران: %s", exc)
        raise self.retry(exc=exc)


@shared_task
def calculate_all_salaries_for_month_task(category_pk: int, year: int, month: int):
    """
    محاسبه و ذخیره حقوق تمام مربیان یک دسته در یک ماه.
    قابل تریگر دستی از پنل مدیریت.
    """
    from .models import TrainingCategory
    from .services.payroll_service import PayrollService
    from .utils.jalali_utils import JalaliMonth

    try:
        category      = TrainingCategory.objects.get(pk=category_pk)
        jalali_month  = JalaliMonth(year, month)
        breakdowns    = PayrollService.calculate_all_coaches_for_month(
            category=category,
            jalali_month=jalali_month,
            processed_by=None,
        )
        saved = 0
        for bd in breakdowns:
            PayrollService.commit_coach_salary(bd, processed_by=None)
            saved += 1

        logger.info(
            "[محاسبه حقوق] دسته %s — %s: %d مربی محاسبه شد.",
            category, jalali_month, saved,
        )
        return {"category": str(category), "month": str(jalali_month), "saved": saved}

    except Exception as exc:
        logger.exception("خطا در تسک محاسبه حقوق: %s", exc)
        raise

# در tasks.py اضافه کنید:
@shared_task
def check_insurance_task():
    from .signals import run_insurance_expiry_check
    return run_insurance_expiry_check(warn_days=30)