"""
futsal_club/tasks.py
─────────────────────────────────────────────────────────────────────
تسک‌های پس‌زمینه Celery

settings.py:
    from celery.schedules import crontab
    CELERY_BEAT_SCHEDULE = {
        'monthly-invoices':  {'task': 'futsal_club.tasks.generate_monthly_invoices_task',
                               'schedule': crontab(hour=6, minute=0, day_of_month=1)},
        'mark-debtors':      {'task': 'futsal_club.tasks.mark_debtors_task',
                               'schedule': crontab(hour=8, minute=0, day_of_month=15)},
        'payment-reminders': {'task': 'futsal_club.tasks.send_payment_reminders_task',
                               'schedule': crontab(hour=9, minute=0, day_of_month=20)},
        'insurance-check':   {'task': 'futsal_club.tasks.check_insurance_expiry_task',
                               'schedule': crontab(hour=7, minute=0)},
        'compress-images':   {'task': 'futsal_club.tasks.compress_receipt_images_task',
                               'schedule': crontab(hour=2, minute=0, day_of_week=0)},
        'cleanup-images':    {'task': 'futsal_club.tasks.cleanup_old_receipt_images_task',
                               'schedule': crontab(hour=3, minute=0, day_of_month=1)},
    }

نیاز: pip install Pillow
"""

from __future__ import annotations
import logging
from io import BytesIO
from pathlib import Path

from celery import shared_task

logger = logging.getLogger(__name__)


# ─────────────────────────────────────────────────────────────────────
# 1. صدور فاکتور ماهانه — یکم هر ماه
# ─────────────────────────────────────────────────────────────────────
@shared_task(bind=True, max_retries=3, default_retry_delay=300)
def generate_monthly_invoices_task(self):
    """صدور فاکتور ماهانه برای تمام دسته‌های فعال. Idempotent."""
    from .services.payroll_service import PayrollService
    from .services.jalali_utils import JalaliMonth
    try:
        month   = JalaliMonth.current()
        results = PayrollService.generate_invoices_all_categories(jalali_month=month)
        total_created = sum(b.created_count for b in results.values())
        total_skipped = sum(b.skipped_count for b in results.values())
        total_errors  = sum(b.error_count   for b in results.values())
        logger.info("[صدور فاکتور %s] ایجاد:%d رد:%d خطا:%d",
                    month, total_created, total_skipped, total_errors)
        return {"month": str(month), "created": total_created,
                "skipped": total_skipped, "errors": total_errors}
    except Exception as exc:
        logger.exception("خطا در صدور فاکتور: %s", exc)
        raise self.retry(exc=exc)


# ─────────────────────────────────────────────────────────────────────
# 2. علامت‌گذاری بدهکاران — پانزدهم هر ماه
# ─────────────────────────────────────────────────────────────────────
@shared_task(bind=True, max_retries=2)
def mark_debtors_task(self):
    """فاکتورهای پرداخت‌نشده‌ی ماه قبل را به وضعیت بدهکار تغییر می‌دهد."""
    from .models import PlayerInvoice
    from .services.jalali_utils import JalaliMonth
    try:
        prev = JalaliMonth.current().prev_month
        updated = PlayerInvoice.objects.filter(
            jalali_year=prev.year, jalali_month=prev.month,
            status=PlayerInvoice.PaymentStatus.PENDING,
        ).update(status=PlayerInvoice.PaymentStatus.DEBTOR)
        logger.info("[بدهکار] %d فاکتور ماه %s → بدهکار", updated, prev)
        return {"updated": updated, "month": str(prev)}
    except Exception as exc:
        raise self.retry(exc=exc)


# ─────────────────────────────────────────────────────────────────────
# 3. یادآوری پرداخت به بازیکنان — بیستم هر ماه
# ─────────────────────────────────────────────────────────────────────
@shared_task(bind=True, max_retries=2)
def send_payment_reminders_task(self):
    """
    به بازیکنانی که شهریه ماه جاری را پرداخت نکرده‌اند اعلان یادآوری می‌فرستد.
    از ارسال تکراری جلوگیری می‌کند.
    """
    from .models import PlayerInvoice, Notification
    from .services.jalali_utils import JalaliMonth
    try:
        month = JalaliMonth.current()
        unpaid = PlayerInvoice.objects.filter(
            jalali_year=month.year, jalali_month=month.month,
            status__in=[PlayerInvoice.PaymentStatus.PENDING,
                        PlayerInvoice.PaymentStatus.DEBTOR],
        ).select_related("player__user", "category")

        count = 0
        for invoice in unpaid:
            if not invoice.player.user:
                continue
            month_str = f"{month.year}/{month.month:02d}"
            already = Notification.objects.filter(
                recipient=invoice.player.user,
                type=Notification.NotificationType.PAYMENT_REMINDER,
                is_read=False,
                message__contains=month_str,
            ).exists()
            if already:
                continue
            label = "بدهکار" if invoice.status == "debtor" else "در انتظار پرداخت"
            Notification.objects.create(
                recipient=invoice.player.user,
                type=Notification.NotificationType.PAYMENT_REMINDER,
                title=f"⚠️ یادآوری شهریه {month.persian_name} {month.year}",
                message=(
                    f"شهریه {month.persian_name} {month.year} دسته «{invoice.category.name}» "
                    f"به مبلغ {invoice.final_amount:,.0f} ریال پرداخت نشده ({label}). "
                    f"لطفاً پرداخت کنید و رسید بانکی را بارگذاری نمایید."
                ),
                related_player=invoice.player,
            )
            count += 1
        logger.info("[یادآوری] %d اعلان ارسال شد — %s", count, month)
        return {"sent": count, "month": str(month)}
    except Exception as exc:
        raise self.retry(exc=exc)


# ─────────────────────────────────────────────────────────────────────
# 4. بررسی بیمه‌های در حال انقضا — روزانه
# ─────────────────────────────────────────────────────────────────────
@shared_task(bind=True, max_retries=3, default_retry_delay=60)
def check_insurance_expiry_task(self):
    from .services.payroll_service import PayrollService
    try:
        count = PayrollService.send_insurance_expiry_notifications(days_ahead=30)
        logger.info("[بیمه] %d اعلان ارسال شد.", count)
        return {"notifications_sent": count}
    except Exception as exc:
        raise self.retry(exc=exc)


# ─────────────────────────────────────────────────────────────────────
# 5. فشرده‌سازی تصاویر رسید — یکشنبه‌ها ساعت ۲ بامداد
# ─────────────────────────────────────────────────────────────────────
@shared_task(bind=True, max_retries=2)
def compress_receipt_images_task(self):
    """
    تصاویر رسید بارگذاری‌شده را فشرده می‌کند.
    حداکثر ۱۲۰۰×۱۲۰۰، کیفیت JPEG 72٪
    مدل‌ها: PlayerInvoice.receipt_image | CoachSalary.bank_receipt | StaffInvoice.bank_receipt
    """
    try:
        from PIL import Image
    except ImportError:
        logger.warning("Pillow نصب نیست — فشرده‌سازی رد شد. pip install Pillow")
        return {"skipped": True}

    from django.core.files.base import ContentFile
    from .models import PlayerInvoice, CoachSalary, StaffInvoice

    MAX_DIM = (1200, 1200)
    QUALITY = 72
    compressed = errors = 0

    def _compress(obj, field_name: str) -> bool:
        field = getattr(obj, field_name, None)
        if not field or not field.name:
            return False
        try:
            field.open("rb")
            img = Image.open(field)
            original_format = img.format or "JPEG"
            w, h = img.size
            already_small = (w <= MAX_DIM[0] and h <= MAX_DIM[1]
                             and original_format == "JPEG")
            if already_small:
                field.close()
                return False
            img.thumbnail(MAX_DIM, Image.LANCZOS)
            if img.mode in ("RGBA", "P", "LA"):
                img = img.convert("RGB")
            buf = BytesIO()
            img.save(buf, format="JPEG", quality=QUALITY, optimize=True)
            buf.seek(0)
            new_name = Path(field.name).stem + "_c.jpg"
            field.save(new_name, ContentFile(buf.read()), save=True)
            return True
        except Exception as e:
            logger.warning("فشرده‌سازی %s pk=%s: %s",
                           obj.__class__.__name__, obj.pk, e)
            return False

    for inv in PlayerInvoice.objects.exclude(receipt_image="").exclude(receipt_image__isnull=True):
        try:
            compressed += _compress(inv, "receipt_image")
        except Exception: errors += 1

    for sal in CoachSalary.objects.exclude(bank_receipt="").exclude(bank_receipt__isnull=True):
        try:
            compressed += _compress(sal, "bank_receipt")
        except Exception: errors += 1

    for si in StaffInvoice.objects.exclude(bank_receipt="").exclude(bank_receipt__isnull=True):
        try:
            compressed += _compress(si, "bank_receipt")
        except Exception: errors += 1

    logger.info("[فشرده‌سازی] %d فشرده، %d خطا", compressed, errors)
    return {"compressed": compressed, "errors": errors}


# ─────────────────────────────────────────────────────────────────────
# 6. حذف تصاویر قدیمی — یکم هر ماه
# ─────────────────────────────────────────────────────────────────────
@shared_task(bind=True, max_retries=2)
def cleanup_old_receipt_images_task(self):
    """
    تصاویر رسیدی که بیش از ۱ سال از صدورشان گذشته را حذف می‌کند.
    فایل فیزیکی حذف می‌شود اما رکورد DB و وضعیت پرداخت دست‌نخورده می‌مانند.
    """
    from django.utils import timezone
    from datetime import timedelta
    from .models import PlayerInvoice, CoachSalary, StaffInvoice

    CUT = timezone.now() - timedelta(days=365)
    deleted = errors = 0

    def _del(obj, fname: str) -> bool:
        field = getattr(obj, fname, None)
        if not field or not field.name:
            return False
        try:
            if field.storage.exists(field.name):
                field.storage.delete(field.name)
            setattr(obj, fname, None)
            obj.save(update_fields=[fname])
            return True
        except Exception as e:
            logger.warning("حذف %s.%s pk=%s: %s",
                           obj.__class__.__name__, fname, obj.pk, e)
            return False

    for inv in PlayerInvoice.objects.filter(created_at__lt=CUT).exclude(
            receipt_image="").exclude(receipt_image__isnull=True):
        try:
            deleted += _del(inv, "receipt_image")
        except Exception: errors += 1

    for sal in CoachSalary.objects.filter(created_at__lt=CUT).exclude(
            bank_receipt="").exclude(bank_receipt__isnull=True):
        try:
            deleted += _del(sal, "bank_receipt")
        except Exception: errors += 1

    for si in StaffInvoice.objects.filter(created_at__lt=CUT).exclude(
            bank_receipt="").exclude(bank_receipt__isnull=True):
        try:
            deleted += _del(si, "bank_receipt")
        except Exception: errors += 1

    logger.info("[پاکسازی] %d تصویر حذف، %d خطا | مرز: %s",
                deleted, errors, CUT.date())
    return {"deleted": deleted, "errors": errors, "cutoff": str(CUT.date())}


# ─────────────────────────────────────────────────────────────────────
# 7. محاسبه حقوق دستی یک دسته — trigger دستی
# ─────────────────────────────────────────────────────────────────────
@shared_task
def calculate_all_salaries_for_month_task(category_pk: int, year: int, month: int):
    from .models import TrainingCategory
    from .services.payroll_service import PayrollService
    from .services.jalali_utils import JalaliMonth
    try:
        category     = TrainingCategory.objects.get(pk=category_pk)
        jalali_month = JalaliMonth(year, month)
        breakdowns   = PayrollService.calculate_all_coaches_for_month(
            category=category, jalali_month=jalali_month, processed_by=None)
        saved = sum(1 for bd in breakdowns
                    if not PayrollService.commit_coach_salary(bd, processed_by=None) is None)
        logger.info("[حقوق] %s — %s: %d مربی", category, jalali_month, saved)
        return {"category": str(category), "month": str(jalali_month), "saved": saved}
    except Exception as exc:
        logger.exception("خطا در محاسبه حقوق: %s", exc)
        raise