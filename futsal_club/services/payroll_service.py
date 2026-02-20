"""
services/payroll_service.py
─────────────────────────────────────────────────────────────────────
لایه سرویس محاسبه حقوق و صدور فاکتور
Coach payroll calculation + monthly player invoice generation.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from decimal import Decimal
from typing import Dict, List, Optional, Tuple

import jdatetime
from django.db import transaction
from django.utils import timezone

from ..models import (
    AttendanceSheet,
    Coach,
    CoachAttendance,
    CoachCategoryRate,
    CoachSalary,
    Notification,
    Player,
    PlayerInvoice,
    TrainingCategory,
)
from ..utils.jalali_utils import JalaliMonth

logger = logging.getLogger(__name__)


# ────────────────────────────────────────────────────────────────────
#  Data Transfer Objects
# ────────────────────────────────────────────────────────────────────

@dataclass
class SalaryBreakdown:
    """
    جزئیات محاسبه حقوق یک مربی در یک دسته و ماه مشخص.
    این شیء قبل از ذخیره در DB برای preview به ویو ارسال می‌شود.
    """
    coach: Coach
    category: TrainingCategory
    jalali_month: JalaliMonth
    sessions_total: int          # کل جلسات ماه
    sessions_attended: int       # جلسات حاضر
    sessions_absent: int
    sessions_excused: int
    session_rate: Decimal
    base_amount: Decimal         # sessions_attended × session_rate
    manual_adjustment: Decimal   # تعدیل دستی مدیر مالی (مثبت یا منفی)
    adjustment_reason: str
    final_amount: Decimal        # base + adjustment
    existing_salary: Optional[CoachSalary] = None

    @property
    def attendance_pct(self) -> float:
        if self.sessions_total == 0:
            return 0.0
        return round(self.sessions_attended / self.sessions_total * 100, 1)


@dataclass
class InvoiceBatch:
    """نتیجه صدور دسته‌ای فاکتورهای ماهانه."""
    jalali_month: JalaliMonth
    created_count: int
    skipped_count: int          # قبلاً وجود داشته
    error_count: int
    invoices: List[PlayerInvoice]
    errors: List[Dict]          # {"player": ..., "reason": ...}


# ────────────────────────────────────────────────────────────────────
#  Coach Payroll Service
# ────────────────────────────────────────────────────────────────────

class PayrollService:
    """
    سرویس محاسبه حقوق مربیان و صدور فاکتور بازیکنان.
    تمام منطق مالی اینجاست.
    """

    # ── 1. Calculate Coach Salary ────────────────────────────────────

    @classmethod
    def calculate_coach_salary(
        cls,
        coach: Coach,
        category: TrainingCategory,
        jalali_month: JalaliMonth,
        manual_adjustment: Decimal = Decimal("0"),
        adjustment_reason: str = "",
    ) -> SalaryBreakdown:
        """
        محاسبه حقوق مربی برای یک دسته و ماه مشخص.

        فرمول:
            base = sessions_attended × session_rate
            final = base + manual_adjustment
        """
        # ── نرخ هر جلسه ────────────────────────────────────────────
        try:
            rate_obj = CoachCategoryRate.objects.get(
                coach=coach, category=category, is_active=True
            )
            session_rate = Decimal(str(rate_obj.session_rate))
        except CoachCategoryRate.DoesNotExist:
            raise ValueError(
                f"نرخ تدریس برای مربی {coach} در دسته {category} تعریف نشده است."
            )

        # ── لیست حضور ──────────────────────────────────────────────
        try:
            sheet = AttendanceSheet.objects.get(
                category=category,
                jalali_year=jalali_month.year,
                jalali_month=jalali_month.month,
            )
        except AttendanceSheet.DoesNotExist:
            raise ValueError(
                f"لیست حضور و غیاب برای {category} — {jalali_month} یافت نشد."
            )

        # ── شمارش جلسات ────────────────────────────────────────────
        sessions_total = sheet.session_dates.count()

        attendance_qs = CoachAttendance.objects.filter(
            session__sheet=sheet, coach=coach
        )
        sessions_attended = attendance_qs.filter(status="present").count()
        sessions_excused  = attendance_qs.filter(status="excused").count()
        sessions_absent   = sessions_total - sessions_attended - sessions_excused

        # ── محاسبه مبالغ ───────────────────────────────────────────
        base_amount  = session_rate * sessions_attended
        final_amount = base_amount + Decimal(str(manual_adjustment))

        # ── رکورد موجود ────────────────────────────────────────────
        existing = CoachSalary.objects.filter(
            coach=coach, category=category, attendance_sheet=sheet
        ).first()

        return SalaryBreakdown(
            coach=coach,
            category=category,
            jalali_month=jalali_month,
            sessions_total=sessions_total,
            sessions_attended=sessions_attended,
            sessions_absent=max(sessions_absent, 0),
            sessions_excused=sessions_excused,
            session_rate=session_rate,
            base_amount=base_amount,
            manual_adjustment=Decimal(str(manual_adjustment)),
            adjustment_reason=adjustment_reason,
            final_amount=final_amount,
            existing_salary=existing,
        )

    @classmethod
    @transaction.atomic
    def commit_coach_salary(
        cls,
        breakdown: SalaryBreakdown,
        processed_by,
    ) -> CoachSalary:
        """
        ذخیره یا به‌روزرسانی رکورد حقوق بر اساس SalaryBreakdown.
        اگر رکورد موجود باشد، به‌روزرسانی می‌شود.
        """
        sheet = AttendanceSheet.objects.get(
            category=breakdown.category,
            jalali_year=breakdown.jalali_month.year,
            jalali_month=breakdown.jalali_month.month,
        )

        salary, created = CoachSalary.objects.update_or_create(
            coach=breakdown.coach,
            category=breakdown.category,
            attendance_sheet=sheet,
            defaults={
                "sessions_attended":   breakdown.sessions_attended,
                "session_rate":        breakdown.session_rate,
                "base_amount":         breakdown.base_amount,
                "manual_adjustment":   breakdown.manual_adjustment,
                "adjustment_reason":   breakdown.adjustment_reason,
                "final_amount":        breakdown.final_amount,
                "status":              CoachSalary.SalaryStatus.CALCULATED,
                "processed_by":        processed_by,
            },
        )

        action = "ایجاد" if created else "به‌روزرسانی"
        logger.info("حقوق %s در %s %s شد. مبلغ: %s ریال",
                    breakdown.coach, breakdown.category, action, breakdown.final_amount)

        # ── اعلان به مربی ──────────────────────────────────────────
        if breakdown.coach.user:
            Notification.objects.create(
                recipient=breakdown.coach.user,
                type=Notification.NotificationType.SALARY_READY,
                title="حقوق محاسبه شد",
                message=(
                    f"حقوق شما برای {breakdown.jalali_month} "
                    f"در دسته {breakdown.category.name} "
                    f"به مبلغ {breakdown.final_amount:,.0f} ریال محاسبه شد."
                ),
            )

        return salary

    @classmethod
    def calculate_all_coaches_for_month(
        cls,
        category: TrainingCategory,
        jalali_month: JalaliMonth,
        processed_by,
    ) -> List[SalaryBreakdown]:
        """
        محاسبه حقوق تمام مربیان فعال یک دسته در یک ماه.
        هنوز ذخیره نمی‌کند — فقط SalaryBreakdown برمی‌گرداند.
        """
        active_rates = CoachCategoryRate.objects.filter(
            category=category, is_active=True
        ).select_related("coach")

        breakdowns = []
        for rate in active_rates:
            try:
                bd = cls.calculate_coach_salary(rate.coach, category, jalali_month)
                breakdowns.append(bd)
            except ValueError as e:
                logger.warning("خطا در محاسبه حقوق %s: %s", rate.coach, e)

        return breakdowns

    # ── 2. Approve & Pay ────────────────────────────────────────────

    @classmethod
    @transaction.atomic
    def approve_salary(cls, salary: CoachSalary, approved_by) -> CoachSalary:
        if salary.status != CoachSalary.SalaryStatus.CALCULATED:
            raise ValueError("فقط حقوق‌های 'محاسبه شده' قابل تأیید هستند.")
        salary.status       = CoachSalary.SalaryStatus.APPROVED
        salary.processed_by = approved_by
        salary.save(update_fields=["status", "processed_by"])
        return salary

    @classmethod
    @transaction.atomic
    def mark_salary_paid(cls, salary: CoachSalary, paid_by) -> CoachSalary:
        if salary.status != CoachSalary.SalaryStatus.APPROVED:
            raise ValueError("فقط حقوق‌های 'تأیید شده' قابل پرداخت هستند.")
        salary.status    = CoachSalary.SalaryStatus.PAID
        salary.paid_at   = timezone.now()
        salary.processed_by = paid_by
        salary.save(update_fields=["status", "paid_at", "processed_by"])
        logger.info("حقوق %s پرداخت شد.", salary)
        return salary

    # ── 3. Player Invoice Generation ────────────────────────────────

    @classmethod
    @transaction.atomic
    def generate_monthly_invoices(
        cls,
        category: TrainingCategory,
        jalali_month: JalaliMonth,
        created_by=None,
    ) -> InvoiceBatch:
        """
        صدور فاکتور ماهانه برای تمام بازیکنان فعال یک دسته.
        این متد idempotent است — اجرای دوباره آن فاکتور تکراری نمی‌سازد.
        """
        active_players = category.players.filter(
            status="approved", is_archived=False
        ).select_related("user")

        created_invoices = []
        skipped = 0
        errors  = []

        for player in active_players:
            try:
                invoice, was_created = PlayerInvoice.objects.get_or_create(
                    player=player,
                    category=category,
                    jalali_year=jalali_month.year,
                    jalali_month=jalali_month.month,
                    defaults={
                        "amount":       category.monthly_fee,
                        "discount":     Decimal("0"),
                        "final_amount": category.monthly_fee,
                        "status":       PlayerInvoice.PaymentStatus.PENDING,
                    },
                )
                if was_created:
                    created_invoices.append(invoice)
                    # اعلان به بازیکن
                    cls._notify_player_invoice(player, invoice, jalali_month)
                else:
                    skipped += 1

            except Exception as exc:
                logger.error("خطا در صدور فاکتور برای %s: %s", player, exc)
                errors.append({"player": str(player), "reason": str(exc)})

        logger.info(
            "فاکتور دسته %s — %s: %d ایجاد، %d رد شد، %d خطا",
            category, jalali_month,
            len(created_invoices), skipped, len(errors),
        )

        return InvoiceBatch(
            jalali_month=jalali_month,
            created_count=len(created_invoices),
            skipped_count=skipped,
            error_count=len(errors),
            invoices=created_invoices,
            errors=errors,
        )

    @classmethod
    def generate_invoices_all_categories(
        cls,
        jalali_month: JalaliMonth,
        created_by=None,
    ) -> Dict[str, InvoiceBatch]:
        """
        صدور فاکتور برای تمام دسته‌های فعال باشگاه در یک ماه.
        مناسب برای تسک Celery که اول ماه اجرا می‌شود.
        """
        results = {}
        for cat in TrainingCategory.objects.filter(is_active=True):
            batch = cls.generate_monthly_invoices(cat, jalali_month, created_by)
            results[cat.name] = batch
        return results

    @staticmethod
    def _notify_player_invoice(
        player: Player,
        invoice: PlayerInvoice,
        jalali_month: JalaliMonth,
    ):
        """ارسال اعلان فاکتور جدید به بازیکن."""
        if player.user:
            Notification.objects.create(
                recipient=player.user,
                type=Notification.NotificationType.INVOICE_DUE,
                title=f"فاکتور {jalali_month.persian_name} {jalali_month.year}",
                message=(
                    f"فاکتور شهریه {jalali_month.persian_name} "
                    f"به مبلغ {invoice.final_amount:,.0f} ریال صادر شد. "
                    "لطفاً در اسرع وقت پرداخت نمایید."
                ),
                related_player=player,
            )

    # ── 4. Insurance Expiry Notifications ───────────────────────────

    @classmethod
    def send_insurance_expiry_notifications(cls, days_ahead: int = 30) -> int:
        """
        بررسی بیمه‌نامه‌های در حال انقضا و ارسال اعلان.
        برای اجرا در یک تسک روزانه طراحی شده.
        Returns: تعداد اعلان‌های ارسال‌شده
        """
        from ..models import CustomUser
        import jdatetime as jdt

        today = jdt.date.today()
        count = 0

        expiring_players = Player.objects.filter(
            insurance_status="active",
            is_archived=False,
            status="approved",
        ).exclude(insurance_expiry_date__isnull=True)

        # پیدا کردن تمام مربیان فنی و مدیران فنی برای اطلاع‌رسانی
        technical_directors = CustomUser.objects.filter(
            is_technical_director=True, is_active=True
        )

        for player in expiring_players:
            if not player.is_insurance_expiring_soon(days_ahead):
                continue

            days_left = (
                player.insurance_expiry_date.togregorian()
                - today.togregorian()
            ).days

            msg = (
                f"بیمه بازیکن {player.first_name} {player.last_name} "
                f"(کد: {player.player_id}) تا {days_left} روز دیگر منقضی می‌شود."
            )

            # اعلان به بازیکن
            if player.user:
                # ✅ اصلاح: get_or_create با فیلدهای غیریکتا ممکن است MultipleObjectsReturned بدهد
                # از filter().exists() استفاده می‌کنیم
                already_notified = Notification.objects.filter(
                    recipient=player.user,
                    type=Notification.NotificationType.INSURANCE_EXPIRY,
                    is_read=False,
                    related_player=player,
                ).exists()
                if not already_notified:
                    Notification.objects.create(
                        recipient=player.user,
                        type=Notification.NotificationType.INSURANCE_EXPIRY,
                        title="هشدار انقضای بیمه",
                        message=msg,
                        related_player=player,
                    )
                    count += 1

            # اعلان به مربیان دسته‌های بازیکن
            for cat in player.categories.filter(is_active=True):
                for rate in CoachCategoryRate.objects.filter(
                    category=cat, is_active=True
                ).select_related("coach__user"):
                    if rate.coach.user:
                        already = Notification.objects.filter(
                            recipient=rate.coach.user,
                            type=Notification.NotificationType.INSURANCE_EXPIRY,
                            is_read=False,
                            related_player=player,
                        ).exists()
                        if not already:
                            Notification.objects.create(
                                recipient=rate.coach.user,
                                type=Notification.NotificationType.INSURANCE_EXPIRY,
                                title=f"هشدار بیمه بازیکن {player.first_name} {player.last_name}",
                                message=msg,
                                related_player=player,
                            )
                            count += 1

            # اعلان به مدیران فنی
            for td in technical_directors:
                already = Notification.objects.filter(
                    recipient=td,
                    type=Notification.NotificationType.INSURANCE_EXPIRY,
                    is_read=False,
                    related_player=player,
                ).exists()
                if not already:
                    Notification.objects.create(
                        recipient=td,
                        type=Notification.NotificationType.INSURANCE_EXPIRY,
                        title=f"هشدار بیمه: {player.first_name} {player.last_name}",
                        message=msg,
                        related_player=player,
                    )
                    count += 1

        logger.info("%d اعلان انقضای بیمه ارسال شد.", count)
        return count

    # ── 5. Invoice Confirm / Receipt ────────────────────────────────

    @classmethod
    @transaction.atomic
    def confirm_invoice_payment(
        cls,
        invoice: PlayerInvoice,
        confirmed_by,
    ) -> PlayerInvoice:
        """تأیید دستی پرداخت یک فاکتور توسط مدیر مالی."""
        if invoice.status not in (
            PlayerInvoice.PaymentStatus.PENDING_CONFIRM,
            PlayerInvoice.PaymentStatus.PENDING,
        ):
            raise ValueError("این فاکتور در وضعیت قابل تأیید نیست.")

        invoice.status       = PlayerInvoice.PaymentStatus.PAID
        invoice.paid_at      = timezone.now()
        invoice.confirmed_by = confirmed_by
        invoice.save(update_fields=["status", "paid_at", "confirmed_by"])
        return invoice

    @classmethod
    @transaction.atomic
    def upload_receipt(
        cls,
        invoice: PlayerInvoice,
        receipt_image,
    ) -> PlayerInvoice:
        """آپلود رسید پرداخت توسط بازیکن."""
        if invoice.status == PlayerInvoice.PaymentStatus.PAID:
            raise ValueError("این فاکتور قبلاً پرداخت شده است.")
        invoice.receipt_image = receipt_image
        invoice.status = PlayerInvoice.PaymentStatus.PENDING_CONFIRM
        invoice.save(update_fields=["receipt_image", "status"])
        return invoice