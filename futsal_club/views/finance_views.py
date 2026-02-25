"""
futsal_club/views/finance_views.py  — نسخه v4 (بازنویسی کامل)
────────────────────────────────────────────────────────────────────
۶ بخش اصلی مدیریت مالی:
1. مدیریت شهریه (داشبورد + لیست دسته‌ها + فاکتور + تأیید رسید)
2. حقوق مربیان (محاسبه + آپلود فیش + تأیید مربی)
3. رسیدهای در انتظار
4. فاکتور دستی (ایجاد + آپلود فیش + تأیید گیرنده)
5. تاریخچه مالی کل
6. هزینه‌ها و درآمد (با فیلتر بازه تاریخ شمسی)
"""
from __future__ import annotations

import logging
from decimal import Decimal
from io import BytesIO
from pathlib import Path

import jdatetime
from django.contrib import messages
from django.contrib.auth.mixins import LoginRequiredMixin
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from django.views import View
from django.db.models import Q, Sum
from django.views.generic import ListView, TemplateView

from ..mixins import RoleRequiredMixin
from ..models import (
    AttendanceSheet,
    Coach,
    CoachCategoryRate,
    CoachSalary,
    CustomUser,
    Expense,
    ExpenseCategory,
    FinancialTransaction,
    Notification,
    PlayerInvoice,
    StaffInvoice,
    TrainingCategory,
)
from ..services.jalali_utils import JalaliMonth, parse_jalali_month_from_request

logger = logging.getLogger(__name__)


# ═══════════════════════════════════════════════════════════════════
#  Mixins
# ═══════════════════════════════════════════════════════════════════

class FinanceAccessMixin(LoginRequiredMixin, RoleRequiredMixin):
    """مدیر مالی + مدیر فنی"""
    allowed_roles = ["finance_manager", "technical_director", "superuser"]

class FinanceOnlyMixin(LoginRequiredMixin, RoleRequiredMixin):
    """فقط مدیر مالی"""
    allowed_roles = ["finance_manager", "superuser"]


# ───────────────────── helpers ─────────────────────────────────────

def _compress_image(image_file, max_dim=1200, quality=72):
    """
    تصویر را فشرده می‌کند و یک ContentFile برمی‌گرداند.
    اگر Pillow نصب نباشد یا خطا پیش بیاید، None برمی‌گرداند.
    """
    try:
        from PIL import Image
        from django.core.files.base import ContentFile

        img = Image.open(image_file)
        img.thumbnail((max_dim, max_dim), Image.LANCZOS)
        if img.mode in ("RGBA", "P", "LA"):
            img = img.convert("RGB")
        buf = BytesIO()
        img.save(buf, format="JPEG", quality=quality, optimize=True)
        buf.seek(0)
        stem = Path(getattr(image_file, 'name', 'img')).stem
        return ContentFile(buf.read(), name=f"{stem}_c.jpg")
    except Exception as e:
        logger.warning("Image compression failed: %s", e)
        return None


def _save_compressed(instance, field_name: str, upload_file) -> bool:
    """فشرده می‌کند و روی instance ذخیره می‌کند. True = موفق"""
    compressed = _compress_image(upload_file)
    field = getattr(instance, field_name)
    if compressed:
        field.save(compressed.name, compressed, save=False)
    else:
        field.save(upload_file.name, upload_file, save=False)
    return True


def _validate_image(upload_file, max_mb=8):
    """بررسی فرمت و اندازه. پیام خطا یا None."""
    allowed = {"image/jpeg", "image/png", "image/webp"}
    ct = getattr(upload_file, 'content_type', '')
    if ct not in allowed:
        return "فقط تصاویر JPEG، PNG و WebP مجاز هستند."
    if upload_file.size > max_mb * 1024 * 1024:
        return f"حداکثر اندازه تصویر {max_mb} مگابایت است."
    return None


# ═══════════════════════════════════════════════════════════════════
#  1. داشبورد مالی
# ═══════════════════════════════════════════════════════════════════

class FinanceDashboardV2View(FinanceAccessMixin, TemplateView):
    """هاب مرکزی با ۶ کارت ناوبری و خلاصه وضعیت"""
    template_name = "payroll/finance_dashboard_v2.html"

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        month = parse_jalali_month_from_request(
            self.request.GET.get("year"),
            self.request.GET.get("month"),
        )
        # آمار شهریه
        inv_qs = PlayerInvoice.objects.filter(
            jalali_year=month.year, jalali_month=month.month
        )
        pending_confirm = PlayerInvoice.objects.filter(
            status=PlayerInvoice.PaymentStatus.PENDING_CONFIRM
        ).count()

        # آمار حقوق
        sal_qs = CoachSalary.objects.filter(
            status__in=[CoachSalary.SalaryStatus.PAID, CoachSalary.SalaryStatus.CONFIRMED]
        )

        # آمار فاکتور دستی در انتظار تأیید
        staff_pending = StaffInvoice.objects.filter(
            status=StaffInvoice.PaymentStatus.PAID
        ).count()

        ctx.update({
            "month":          month,
            "prev_month":     month.prev_month,
            "next_month":     month.next_month,
            "categories":     TrainingCategory.objects.filter(is_active=True).order_by("name"),
            # رسیدهای در انتظار تأیید
            "pending_receipt_count": pending_confirm,
            "staff_pending_count":   staff_pending,
            # آمار شهریه ماه
            "invoice_stats": {
                "paid":            inv_qs.filter(status="paid").count(),
                "pending":         inv_qs.filter(status="pending").count(),
                "debtor":          inv_qs.filter(status="debtor").count(),
                "pending_confirm": inv_qs.filter(status="pending_confirm").count(),
                "paid_amount":     inv_qs.filter(status="paid").aggregate(s=Sum("final_amount"))["s"] or 0,
            },
        })
        return ctx


# ═══════════════════════════════════════════════════════════════════
#  2. مدیریت شهریه — InvoiceListView (دسته × ماه)
# ═══════════════════════════════════════════════════════════════════

class TuitionCategoryListView(FinanceAccessMixin, TemplateView):
    """لیست دسته‌های آموزشی با آمار شهریه ماه"""
    template_name = "payroll/tuition_category_list.html"

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        month = parse_jalali_month_from_request(
            self.request.GET.get("year"),
            self.request.GET.get("month"),
        )
        categories = TrainingCategory.objects.filter(is_active=True).prefetch_related("invoices")
        cat_data = []
        for cat in categories:
            inv = cat.invoices.filter(jalali_year=month.year, jalali_month=month.month)
            cat_data.append({
                "category":       cat,
                "total":          inv.count(),
                "paid":           inv.filter(status="paid").count(),
                "pending":        inv.filter(status__in=["pending","debtor"]).count(),
                "pending_confirm":inv.filter(status="pending_confirm").count(),
                "collected":      inv.filter(status="paid").aggregate(s=Sum("final_amount"))["s"] or 0,
            })
        ctx.update({
            "month":     month,
            "prev_month":month.prev_month,
            "next_month":month.next_month,
            "cat_data":  cat_data,
        })
        return ctx


class InvoiceListView(FinanceAccessMixin, ListView):
    """لیست فاکتورهای یک دسته × ماه + تأیید رسید"""
    template_name       = "payroll/invoice_list.html"
    context_object_name = "invoices"
    paginate_by         = 40

    def _get_month(self):
        return parse_jalali_month_from_request(
            self.request.GET.get("year") or self.request.POST.get("year"),
            self.request.GET.get("month") or self.request.POST.get("month"),
        )

    def get_queryset(self):
        cat   = get_object_or_404(TrainingCategory, pk=self.kwargs["category_pk"])
        month = self._get_month()
        qs    = PlayerInvoice.objects.filter(
            category=cat,
            jalali_year=month.year,
            jalali_month=month.month,
        ).select_related("player", "confirmed_by").order_by("player__last_name")
        st = self.request.GET.get("status", "")
        if st:
            qs = qs.filter(status=st)
        return qs

    def get_context_data(self, **kwargs):
        ctx      = super().get_context_data(**kwargs)
        month    = self._get_month()
        category = get_object_or_404(TrainingCategory, pk=self.kwargs["category_pk"])
        qs_all   = PlayerInvoice.objects.filter(
            category=category, jalali_year=month.year, jalali_month=month.month
        )
        ctx.update({
            "category":   category,
            "month":      month,
            "prev_month": month.prev_month,
            "next_month": month.next_month,
            "stats": {
                "paid":            qs_all.filter(status="paid").count(),
                "pending":         qs_all.filter(status="pending").count(),
                "debtor":          qs_all.filter(status="debtor").count(),
                "pending_confirm": qs_all.filter(status="pending_confirm").count(),
                "paid_amount":     qs_all.filter(status="paid").aggregate(s=Sum("final_amount"))["s"] or 0,
            },
            "pending_confirm_count": qs_all.filter(status="pending_confirm").count(),
            "status_filter": self.request.GET.get("status", ""),
            "status_choices": PlayerInvoice.PaymentStatus.choices,
        })
        return ctx


class GenerateMonthlyInvoicesView(FinanceOnlyMixin, View):
    """صدور فاکتور ماهانه برای یک دسته"""
    http_method_names = ["post"]

    def post(self, request, category_pk: int):
        from ..services.payroll_service import PayrollService
        category = get_object_or_404(TrainingCategory, pk=category_pk)
        month    = parse_jalali_month_from_request(
            request.POST.get("year"), request.POST.get("month")
        )
        batch = PayrollService.generate_monthly_invoices(
            category=category, jalali_month=month, created_by=request.user
        )
        messages.success(request,
            f"{batch.created_count} فاکتور برای {month} ایجاد شد. "
            f"{batch.skipped_count} مورد تکراری رد شد.")
        return redirect(f"{request.path.replace('/generate/','/')}?year={month.year}&month={month.month}"
                        .replace(f"invoices/generate/{category_pk}/",
                                 f"invoices/category/{category_pk}/"))


class GenerateAllCategoryInvoicesView(FinanceOnlyMixin, View):
    """صدور فاکتور برای همه دسته‌ها"""
    http_method_names = ["post"]

    def post(self, request):
        from ..services.payroll_service import PayrollService
        month   = parse_jalali_month_from_request(
            request.POST.get("year"), request.POST.get("month")
        )
        results = PayrollService.generate_invoices_all_categories(
            jalali_month=month, created_by=request.user
        )
        total = sum(b.created_count for b in results.values())
        messages.success(request, f"{total} فاکتور برای {month} در همه دسته‌ها صادر شد.")
        from django.urls import reverse
        return redirect(
            reverse("payroll:tuition-categories") + f"?year={month.year}&month={month.month}"
        )


class ConfirmInvoicePaymentView(FinanceOnlyMixin, View):
    """تأیید رسید پرداخت شهریه بازیکن"""
    http_method_names = ["post"]

    def post(self, request, invoice_pk: int):
        invoice = get_object_or_404(
            PlayerInvoice, pk=invoice_pk,
            status=PlayerInvoice.PaymentStatus.PENDING_CONFIRM
        )
        notes = request.POST.get("notes", "").strip()
        invoice.status       = PlayerInvoice.PaymentStatus.PAID
        invoice.paid_at      = timezone.now()
        invoice.confirmed_by = request.user
        if notes:
            invoice.notes = notes
        invoice.save(update_fields=["status", "paid_at", "confirmed_by", "notes", "updated_at"])

        # ثبت تراکنش
        if invoice.player.user:
            FinancialTransaction.objects.get_or_create(
                user=invoice.player.user,
                tx_type=FinancialTransaction.TxType.INVOICE_PAID,
                player_invoice=invoice,
                defaults={
                    "direction":    FinancialTransaction.Direction.DEBIT,
                    "amount":       invoice.final_amount,
                    "description":  f"شهریه «{invoice.category.name}» {invoice.jalali_year}/{invoice.jalali_month:02d}",
                    "performed_by": request.user,
                },
            )
            Notification.objects.create(
                recipient=invoice.player.user,
                type=Notification.NotificationType.INVOICE_PAID,
                title=f"✅ شهریه {invoice.jalali_year}/{invoice.jalali_month:02d} تأیید شد",
                message=f"شهریه دسته «{invoice.category.name}» تأیید شد."
                        + (f" یادداشت: {notes}" if notes else ""),
                related_player=invoice.player,
            )
        messages.success(request, f"رسید {invoice.player} تأیید شد.")
        return redirect(
            request.POST.get("next") or
            f"/payroll/invoices/category/{invoice.category_id}/"
        )


class InvoiceStatusUpdateView(FinanceOnlyMixin, View):
    """تغییر وضعیت دستی یک فاکتور"""
    http_method_names = ["post"]

    def post(self, request, invoice_pk: int):
        invoice    = get_object_or_404(PlayerInvoice, pk=invoice_pk)
        new_status = request.POST.get("new_status", "")
        valid = [c[0] for c in PlayerInvoice.PaymentStatus.choices]
        if new_status in valid:
            invoice.status = new_status
            if new_status == "paid":
                invoice.paid_at      = timezone.now()
                invoice.confirmed_by = request.user
            invoice.save(update_fields=["status", "paid_at", "confirmed_by", "updated_at"])
            messages.success(request, "وضعیت فاکتور به‌روز شد.")
        return redirect(request.POST.get("redirect_to") or "payroll:player-payment-status")


class SendPaymentReminderView(FinanceOnlyMixin, View):
    """ارسال یادآوری پرداخت"""
    http_method_names = ["post"]

    def post(self, request):
        invoice_pk = request.POST.get("invoice_pk", "").strip()
        custom_msg = request.POST.get("custom_message", "").strip()

        if invoice_pk:
            invoice = get_object_or_404(PlayerInvoice, pk=invoice_pk)
            if not invoice.player.user:
                messages.warning(request, "این بازیکن حساب کاربری ندارد.")
                return redirect(request.META.get("HTTP_REFERER", "payroll:player-payment-status"))

            month_str = f"{invoice.jalali_year}/{invoice.jalali_month:02d}"
            Notification.objects.create(
                recipient=invoice.player.user,
                type=Notification.NotificationType.PAYMENT_REMINDER,
                title=f"⚠️ یادآوری شهریه {month_str}",
                message=custom_msg or (
                    f"شهریه {month_str} دسته «{invoice.category.name}» "
                    f"به مبلغ {invoice.final_amount:,.0f} ریال پرداخت نشده. "
                    f"لطفاً پرداخت و رسید را بارگذاری کنید."
                ),
                related_player=invoice.player,
            )
            messages.success(request, f"یادآوری به {invoice.player} ارسال شد.")

        else:
            month = parse_jalali_month_from_request(
                request.POST.get("year"), request.POST.get("month")
            )
            unpaid = PlayerInvoice.objects.filter(
                jalali_year=month.year, jalali_month=month.month,
                status__in=["pending", "debtor"],
            ).select_related("player__user", "category")
            count = 0
            for inv in unpaid:
                if not inv.player.user:
                    continue
                month_str = f"{month.year}/{month.month:02d}"
                Notification.objects.create(
                    recipient=inv.player.user,
                    type=Notification.NotificationType.PAYMENT_REMINDER,
                    title=f"⚠️ یادآوری شهریه {month_str}",
                    message=custom_msg or (
                        f"شهریه {month_str} دسته «{inv.category.name}» "
                        f"به مبلغ {inv.final_amount:,.0f} ریال پرداخت نشده."
                    ),
                    related_player=inv.player,
                )
                count += 1
            messages.success(request, f"یادآوری به {count} بازیکن ارسال شد.")

        return redirect(request.META.get("HTTP_REFERER", "payroll:player-payment-status"))


class PlayerPaymentStatusView(FinanceAccessMixin, TemplateView):
    """نمای کلی وضعیت پرداخت بازیکنان"""
    template_name = "payroll/player_payment_status.html"

    def get_context_data(self, **kwargs):
        ctx   = super().get_context_data(**kwargs)
        month = parse_jalali_month_from_request(
            self.request.GET.get("year"),
            self.request.GET.get("month"),
        )
        categories = TrainingCategory.objects.filter(is_active=True).order_by("name")
        cat_pk     = self.request.GET.get("category", "")
        selected_cat = None
        if cat_pk:
            try:
                selected_cat = categories.get(pk=int(cat_pk))
            except (TrainingCategory.DoesNotExist, ValueError):
                pass

        if selected_cat:
            invoices = PlayerInvoice.objects.filter(
                category=selected_cat, jalali_year=month.year, jalali_month=month.month,
            ).select_related("player", "confirmed_by").order_by("player__last_name")
        else:
            invoices = PlayerInvoice.objects.filter(
                jalali_year=month.year, jalali_month=month.month,
            ).select_related("player", "category", "confirmed_by").order_by("category__name", "player__last_name")

        stats = {
            "paid":            invoices.filter(status="paid").count(),
            "pending":         invoices.filter(status="pending").count(),
            "debtor":          invoices.filter(status="debtor").count(),
            "pending_confirm": invoices.filter(status="pending_confirm").count(),
            "total_collected": invoices.filter(status="paid").aggregate(s=Sum("final_amount"))["s"] or 0,
            "total_pending":   invoices.filter(status__in=["pending","debtor"]).aggregate(s=Sum("final_amount"))["s"] or 0,
        }
        ctx.update({
            "month":          month,
            "prev_month":     month.prev_month,
            "next_month":     month.next_month,
            "categories":     categories,
            "selected_cat":   selected_cat,
            "invoices":       invoices,
            "stats":          stats,
            "status_choices": PlayerInvoice.PaymentStatus.choices,
        })
        return ctx


# ═══════════════════════════════════════════════════════════════════
#  3. رسیدهای در انتظار تأیید
# ═══════════════════════════════════════════════════════════════════

class PendingReceiptsView(FinanceOnlyMixin, ListView):
    """همه رسیدهای بارگذاری‌شده‌ای که هنوز تأیید نشده‌اند"""
    template_name       = "payroll/pending_receipts.html"
    context_object_name = "invoices"
    paginate_by         = 20

    def get_queryset(self):
        return PlayerInvoice.objects.filter(
            status=PlayerInvoice.PaymentStatus.PENDING_CONFIRM
        ).select_related("player", "category").order_by("jalali_year", "jalali_month", "player__last_name")

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx["total_pending"] = self.get_queryset().count()
        # حقوق‌های در انتظار تأیید مربی
        ctx["salary_pending"] = CoachSalary.objects.filter(
            status=CoachSalary.SalaryStatus.PAID,
            bank_receipt__isnull=False,
        ).exclude(bank_receipt="").select_related("coach", "category", "attendance_sheet")[:10]
        # فاکتورهای دستی در انتظار تأیید گیرنده
        ctx["staff_pending"] = StaffInvoice.objects.filter(
            status=StaffInvoice.PaymentStatus.PAID,
            bank_receipt__isnull=False,
        ).exclude(bank_receipt="").select_related("recipient", "created_by")[:10]
        return ctx

    def post(self, request):
        invoice_pk = request.POST.get("invoice_pk", "")
        action     = request.POST.get("action", "")
        notes      = request.POST.get("notes", "").strip()

        invoice = get_object_or_404(
            PlayerInvoice, pk=invoice_pk,
            status=PlayerInvoice.PaymentStatus.PENDING_CONFIRM
        )
        if action == "confirm":
            invoice.status       = PlayerInvoice.PaymentStatus.PAID
            invoice.paid_at      = timezone.now()
            invoice.confirmed_by = request.user
            if notes:
                invoice.notes = notes
            invoice.save(update_fields=["status", "paid_at", "confirmed_by", "notes", "updated_at"])

            if invoice.player.user:
                FinancialTransaction.objects.get_or_create(
                    user=invoice.player.user, player_invoice=invoice,
                    tx_type=FinancialTransaction.TxType.INVOICE_PAID,
                    defaults={
                        "direction":    FinancialTransaction.Direction.DEBIT,
                        "amount":       invoice.final_amount,
                        "description":  f"شهریه «{invoice.category.name}» {invoice.jalali_year}/{invoice.jalali_month:02d}",
                        "performed_by": request.user,
                    },
                )
                Notification.objects.create(
                    recipient=invoice.player.user,
                    type=Notification.NotificationType.INVOICE_PAID,
                    title=f"✅ شهریه {invoice.jalali_year}/{invoice.jalali_month:02d} تأیید شد",
                    message=f"شهریه دسته «{invoice.category.name}» تأیید شد."
                            + (f" یادداشت: {notes}" if notes else ""),
                    related_player=invoice.player,
                )
            messages.success(request, f"رسید {invoice.player} تأیید شد.")

        elif action == "reject":
            invoice.status        = PlayerInvoice.PaymentStatus.PENDING
            invoice.receipt_image = None
            invoice.save(update_fields=["status", "receipt_image", "updated_at"])
            if invoice.player.user:
                Notification.objects.create(
                    recipient=invoice.player.user,
                    type=Notification.NotificationType.INVOICE_DUE,
                    title=f"❌ رسید شهریه {invoice.jalali_year}/{invoice.jalali_month:02d} رد شد",
                    message=f"رسید شهریه دسته «{invoice.category.name}» رد شد."
                            + (f" دلیل: {notes}" if notes else " لطفاً رسید صحیح ارسال کنید."),
                    related_player=invoice.player,
                )
            messages.warning(request, f"رسید {invoice.player} رد شد.")

        return redirect("payroll:pending-receipts")


# ═══════════════════════════════════════════════════════════════════
#  بازیکن: فاکتورهای من + آپلود رسید
# ═══════════════════════════════════════════════════════════════════

class PlayerInvoicesView(LoginRequiredMixin, TemplateView):
    """صفحه بازیکن: مشاهده فاکتور و بارگذاری رسید"""
    template_name = "payroll/player_invoices.html"

    def get(self, request, *args, **kwargs):
        if not hasattr(request.user, "player_profile"):
            return render(request, self.template_name, {"no_player": True})
        return super().get(request, *args, **kwargs)

    def get_context_data(self, **kwargs):
        ctx    = super().get_context_data(**kwargs)
        player = self.request.user.player_profile
        month  = parse_jalali_month_from_request(
            self.request.GET.get("year"),
            self.request.GET.get("month"),
        )
        all_invoices   = PlayerInvoice.objects.filter(player=player).select_related(
            "category", "confirmed_by").order_by("-jalali_year", "-jalali_month")
        month_invoices = all_invoices.filter(
            jalali_year=month.year, jalali_month=month.month
        )
        ctx.update({
            "player":         player,
            "month":          month,
            "prev_month":     month.prev_month,
            "next_month":     month.next_month,
            "month_invoices": month_invoices,
            "all_invoices":   all_invoices[:12],
        })
        return ctx

    def post(self, request, *args, **kwargs):
        if not hasattr(request.user, "player_profile"):
            return redirect("payroll:player-invoices")
        invoice = get_object_or_404(
            PlayerInvoice, pk=request.POST.get("invoice_pk", ""),
            player=request.user.player_profile
        )
        if invoice.status == PlayerInvoice.PaymentStatus.PAID:
            messages.warning(request, "این فاکتور قبلاً پرداخت شده است.")
            return redirect("payroll:player-invoices")

        receipt = request.FILES.get("receipt_image")
        if not receipt:
            messages.error(request, "فایل رسید انتخاب نشده است.")
            return redirect("payroll:player-invoices")

        err = _validate_image(receipt)
        if err:
            messages.error(request, err)
            return redirect("payroll:player-invoices")

        # فشرده‌سازی و ذخیره
        compressed = _compress_image(receipt)
        if compressed:
            invoice.receipt_image.save(compressed.name, compressed, save=False)
        else:
            invoice.receipt_image.save(receipt.name, receipt, save=False)
        invoice.status = PlayerInvoice.PaymentStatus.PENDING_CONFIRM
        invoice.save(update_fields=["receipt_image", "status", "updated_at"])

        # اعلان به مدیران مالی
        for fm in CustomUser.objects.filter(is_finance_manager=True, is_active=True):
            Notification.objects.create(
                recipient=fm,
                type=Notification.NotificationType.RECEIPT_UPLOADED,
                title=f"📎 رسید جدید: {invoice.player.first_name} {invoice.player.last_name}",
                message=(
                    f"{invoice.player.first_name} {invoice.player.last_name} رسید شهریه "
                    f"{invoice.jalali_year}/{invoice.jalali_month:02d} «{invoice.category.name}» "
                    f"بارگذاری کرد."
                ),
                related_player=invoice.player,
            )
        messages.success(request, "رسید بارگذاری شد — در انتظار تأیید مدیر مالی.")
        return redirect("payroll:player-invoices")


# ═══════════════════════════════════════════════════════════════════
#  4. حقوق مربیان
# ═══════════════════════════════════════════════════════════════════

class SalaryListView(FinanceAccessMixin, ListView):
    """لیست حقوق مربیان یک دسته × ماه"""
    template_name       = "payroll/salary_list.html"
    context_object_name = "salaries"

    def _get_params(self):
        self.month    = parse_jalali_month_from_request(
            self.request.GET.get("year") or self.request.POST.get("year"),
            self.request.GET.get("month") or self.request.POST.get("month"),
        )
        self.category = get_object_or_404(TrainingCategory, pk=self.kwargs["category_pk"])

    def get(self, request, *args, **kwargs):
        self._get_params()
        return super().get(request, *args, **kwargs)

    def post(self, request, *args, **kwargs):
        self._get_params()
        return super().get(request, *args, **kwargs)

    def get_queryset(self):
        if not hasattr(self, 'month'):
            self._get_params()
        return CoachSalary.objects.filter(
            category=self.category,
            attendance_sheet__jalali_year=self.month.year,
            attendance_sheet__jalali_month=self.month.month,
        ).select_related("coach", "attendance_sheet", "processed_by").order_by("coach__last_name")

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        qs  = self.get_queryset()
        ctx.update({
            "category":   self.category,
            "month":      self.month,
            "prev_month": self.month.prev_month,
            "next_month": self.month.next_month,
            "paid_count": qs.filter(status__in=["paid","confirmed"]).count(),
            "total_amount": qs.aggregate(s=Sum("final_amount"))["s"] or 0,
        })
        return ctx


class BulkSalaryCalculateView(FinanceAccessMixin, TemplateView):
    """محاسبه دسته‌جمعی حقوق همه مربیان یک دسته"""
    template_name = "payroll/bulk_salary.html"

    def _get_params(self):
        self.month    = parse_jalali_month_from_request(
            self.request.GET.get("year") or self.request.POST.get("year"),
            self.request.GET.get("month") or self.request.POST.get("month"),
        )
        self.category = get_object_or_404(TrainingCategory, pk=self.kwargs["category_pk"])

    def get(self, request, *args, **kwargs):
        self._get_params()
        return super().get(request, *args, **kwargs)

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        from ..services.payroll_service import PayrollService
        try:
            breakdowns = PayrollService.calculate_all_coaches_for_month(
                category=self.category,
                jalali_month=self.month,
                processed_by=self.request.user,
            )
        except Exception:
            breakdowns = []
        ctx.update({
            "category":   self.category,
            "month":      self.month,
            "prev_month": self.month.prev_month,
            "next_month": self.month.next_month,
            "breakdowns": breakdowns,
            "total":      sum(getattr(bd, "final_amount", 0) for bd in breakdowns),
        })
        return ctx

    def post(self, request, *args, **kwargs):
        self._get_params()
        from ..services.payroll_service import PayrollService
        try:
            breakdowns = PayrollService.calculate_all_coaches_for_month(
                category=self.category,
                jalali_month=self.month,
                processed_by=request.user,
            )
        except Exception as e:
            messages.error(request, f"خطا در محاسبه: {e}")
            return redirect("payroll:salary-list", category_pk=self.category.pk)

        saved = 0
        for bd in breakdowns:
            # خواندن تعدیل دستی از POST
            adj_key    = f"adjustment_{bd.coach.pk}"
            reason_key = f"reason_{bd.coach.pk}"
            try:
                adj = Decimal(request.POST.get(adj_key, "0") or "0")
            except Exception:
                adj = Decimal("0")
            reason = request.POST.get(reason_key, "")
            if adj:
                bd.manual_adjustment = adj
                bd.adjustment_reason = reason
                bd.final_amount      = bd.base_amount + adj
            PayrollService.commit_coach_salary(bd, processed_by=request.user)
            saved += 1

        messages.success(request, f"حقوق {saved} مربی برای {self.month} ذخیره شد.")
        return redirect(
            f"/payroll/salary/category/{self.category.pk}/"
            f"?year={self.month.year}&month={self.month.month}"
        )


class CoachSalaryCalculateView(FinanceAccessMixin, TemplateView):
    """محاسبه حقوق یک مربی با امکان تعدیل دستی"""
    template_name = "payroll/salary_preview.html"

    def _get_params(self):
        self.month    = parse_jalali_month_from_request(
            self.request.GET.get("year") or self.request.POST.get("year"),
            self.request.GET.get("month") or self.request.POST.get("month"),
        )
        self.category = get_object_or_404(TrainingCategory, pk=self.kwargs["category_pk"])
        self.coach    = get_object_or_404(Coach, pk=self.kwargs["coach_pk"])

    def get(self, request, *args, **kwargs):
        self._get_params()
        return super().get(request, *args, **kwargs)

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        from ..services.payroll_service import PayrollService
        try:
            bd = PayrollService.calculate_coach_salary(
                coach=self.coach, category=self.category, jalali_month=self.month,
            )
        except Exception:
            bd = None
        existing = CoachSalary.objects.filter(
            coach=self.coach, category=self.category,
            attendance_sheet__jalali_year=self.month.year,
            attendance_sheet__jalali_month=self.month.month,
        ).first()
        ctx.update({
            "coach":      self.coach,
            "category":   self.category,
            "month":      self.month,
            "prev_month": self.month.prev_month,
            "next_month": self.month.next_month,
            "breakdown":  bd,
            "existing":   existing,
        })
        return ctx

    def post(self, request, *args, **kwargs):
        self._get_params()
        from ..services.payroll_service import PayrollService
        try:
            adj    = Decimal(request.POST.get("manual_adjustment", "0") or "0")
            reason = request.POST.get("adjustment_reason", "")
            bd     = PayrollService.calculate_coach_salary(
                coach=self.coach, category=self.category, jalali_month=self.month,
                manual_adjustment=adj, adjustment_reason=reason,
            )
            PayrollService.commit_coach_salary(bd, processed_by=request.user)
            messages.success(request, f"حقوق {self.coach} برای {self.month} ذخیره شد.")
        except Exception as e:
            messages.error(request, f"خطا: {e}")
        return redirect(
            f"/payroll/salary/category/{self.category.pk}/"
            f"?year={self.month.year}&month={self.month.month}"
        )


class ApproveSalaryView(FinanceOnlyMixin, View):
    http_method_names = ["post"]

    def post(self, request, salary_pk: int):
        salary = get_object_or_404(CoachSalary, pk=salary_pk, status=CoachSalary.SalaryStatus.CALCULATED)
        salary.status = CoachSalary.SalaryStatus.APPROVED
        salary.save(update_fields=["status"])
        messages.success(request, f"حقوق {salary.coach} تأیید شد.")
        return redirect(request.META.get("HTTP_REFERER", "payroll:coach-payroll-summary"))


class MarkSalaryPaidView(FinanceOnlyMixin, View):
    """مدیر مالی فیش بانکی آپلود می‌کند → وضعیت PAID + اعلان به مربی"""
    http_method_names = ["post"]

    def post(self, request, salary_pk: int):
        salary  = get_object_or_404(CoachSalary, pk=salary_pk)
        if salary.status == CoachSalary.SalaryStatus.CALCULATED:
            salary.status = CoachSalary.SalaryStatus.APPROVED
        receipt = request.FILES.get("bank_receipt")
        if not receipt:
            messages.error(request, "بارگذاری فیش بانکی الزامی است.")
            return redirect(request.META.get("HTTP_REFERER", "payroll:coach-payroll-summary"))

        err = _validate_image(receipt)
        if err:
            messages.error(request, err)
            return redirect(request.META.get("HTTP_REFERER", "payroll:coach-payroll-summary"))

        # فشرده‌سازی
        compressed = _compress_image(receipt)
        salary.bank_receipt.save(
            compressed.name if compressed else receipt.name,
            compressed or receipt, save=False
        )
        salary.status       = CoachSalary.SalaryStatus.PAID
        salary.paid_at      = timezone.now()
        salary.processed_by = request.user
        salary.save(update_fields=["bank_receipt", "status", "paid_at", "processed_by"])

        # اعلان به مربی با لینک تأیید
        if salary.coach.user:
            month_str = (
                f"{salary.attendance_sheet.jalali_year}/"
                f"{salary.attendance_sheet.jalali_month:02d}"
            )
            from django.urls import reverse
            confirm_url = request.build_absolute_uri(
                reverse("payroll:coach-confirm-salary", args=[salary.pk])
            )
            Notification.objects.create(
                recipient=salary.coach.user,
                type=Notification.NotificationType.SALARY_PAID,
                title=f"💰 فیش حقوق {month_str} آماده تأیید",
                message=(
                    f"فیش حقوق دسته «{salary.category.name}» ماه {month_str} "
                    f"به مبلغ {salary.final_amount:,.0f} ریال بارگذاری شد. "
                    f"لطفاً رسید را بررسی و تأیید کنید: {confirm_url}"
                ),
            )
        messages.success(request, f"فیش حقوق {salary.coach} آپلود و ارسال شد — منتظر تأیید مربی.")
        return redirect(request.META.get("HTTP_REFERER", "payroll:coach-payroll-summary"))


class CoachConfirmSalaryView(LoginRequiredMixin, View):
    """مربی فیش را می‌بیند و تأیید یا رد می‌کند"""
    template_name = "payroll/coach_confirm_salary.html"

    def get(self, request, salary_pk: int):
        salary = get_object_or_404(CoachSalary, pk=salary_pk)
        # فقط مربی صاحب حقوق
        if not (hasattr(request.user, "coach_profile") and
                salary.coach == request.user.coach_profile):
            messages.error(request, "دسترسی غیرمجاز.")
            return redirect("payroll:my-financial-history")
        return render(request, self.template_name, {"salary": salary})

    def post(self, request, salary_pk: int):
        salary = get_object_or_404(CoachSalary, pk=salary_pk)
        if not (hasattr(request.user, "coach_profile") and
                salary.coach == request.user.coach_profile):
            messages.error(request, "دسترسی غیرمجاز.")
            return redirect("payroll:my-financial-history")

        action = request.POST.get("action", "")
        if action == "confirm" and salary.status == CoachSalary.SalaryStatus.PAID:
            salary.status             = CoachSalary.SalaryStatus.CONFIRMED
            salary.coach_confirmed    = True
            salary.coach_confirmed_at = timezone.now()
            salary.save(update_fields=["status", "coach_confirmed", "coach_confirmed_at"])

            # ثبت تراکنش + اعلان به مدیر مالی
            if salary.coach.user:
                FinancialTransaction.objects.get_or_create(
                    user=salary.coach.user,
                    tx_type=FinancialTransaction.TxType.SALARY_PAID,
                    coach_salary=salary,
                    defaults={
                        "direction":    FinancialTransaction.Direction.CREDIT,
                        "amount":       salary.final_amount,
                        "description":  f"حقوق «{salary.category.name}»",
                        "performed_by": request.user,
                    },
                )
            for fm in CustomUser.objects.filter(is_finance_manager=True, is_active=True):
                Notification.objects.create(
                    recipient=fm,
                    type=Notification.NotificationType.GENERAL,
                    title=f"✅ مربی {salary.coach} حقوق را تأیید کرد",
                    message=(
                        f"مربی {salary.coach} دریافت حقوق {salary.final_amount:,.0f} ریال "
                        f"دسته «{salary.category.name}» را تأیید کرد."
                    ),
                )
            messages.success(request, "دریافت حقوق با موفقیت تأیید شد.")

        elif action == "dispute":
            note = request.POST.get("note", "").strip()
            for fm in CustomUser.objects.filter(is_finance_manager=True, is_active=True):
                Notification.objects.create(
                    recipient=fm,
                    type=Notification.NotificationType.GENERAL,
                    title=f"⚠️ اعتراض مربی {salary.coach} به حقوق",
                    message=(
                        f"مربی {salary.coach} نسبت به حقوق "
                        f"{salary.final_amount:,.0f} ریال اعتراض دارد. "
                        + (f"توضیح: {note}" if note else "")
                    ),
                )
            messages.warning(request, "اعتراض شما ثبت و به مدیر مالی اطلاع داده شد.")

        return redirect("payroll:my-financial-history")


# ═══════════════════════════════════════════════════════════════════
#  5. فاکتور دستی — StaffInvoice
# ═══════════════════════════════════════════════════════════════════

class StaffInvoiceListView(FinanceOnlyMixin, ListView):
    template_name       = "payroll/staff_invoice_list.html"
    context_object_name = "invoices"
    paginate_by         = 25

    def get_queryset(self):
        qs = StaffInvoice.objects.select_related("recipient", "created_by").order_by("-created_at")
        q  = self.request.GET.get("q", "").strip()
        st = self.request.GET.get("status", "")
        if q:
            qs = qs.filter(Q(title__icontains=q) | Q(recipient__first_name__icontains=q) |
                           Q(recipient__last_name__icontains=q))
        if st:
            qs = qs.filter(status=st)
        return qs

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx.update({
            "q":              self.request.GET.get("q", ""),
            "status_filter":  self.request.GET.get("status", ""),
            "status_choices": StaffInvoice.PaymentStatus.choices,
        })
        return ctx


class StaffInvoiceCreateView(FinanceOnlyMixin, View):
    template_name = "payroll/staff_invoice_create.html"

    def get(self, request):
        users = CustomUser.objects.filter(is_active=True).exclude(
            id=request.user.id
        ).order_by("last_name", "first_name")
        return render(request, self.template_name, {"users": users})

    def post(self, request):
        users = CustomUser.objects.filter(is_active=True).exclude(id=request.user.id)
        try:
            recipient = CustomUser.objects.get(pk=request.POST["recipient_id"])
            title     = request.POST["title"].strip()
            amount    = Decimal(request.POST["amount"])
            desc      = request.POST.get("description", "").strip()
        except Exception as e:
            messages.error(request, f"خطا در ورودی: {e}")
            return render(request, self.template_name, {"users": users, "prev": request.POST})

        inv = StaffInvoice.objects.create(
            recipient=recipient, title=title, amount=amount,
            description=desc, created_by=request.user,
        )
        Notification.objects.create(
            recipient=recipient,
            type=Notification.NotificationType.STAFF_INVOICE,
            title=f"📄 فاکتور جدید: {title}",
            message=f"یک فاکتور به مبلغ {amount:,.0f} ریال برای شما صادر شد.",
        )
        messages.success(request, f"فاکتور «{title}» برای {recipient.get_full_name()} صادر شد.")
        return redirect("payroll:staff-invoice-list")


class StaffInvoiceReceiptUploadView(FinanceOnlyMixin, View):
    """مدیر مالی فیش پرداخت آپلود می‌کند → وضعیت PAID"""
    http_method_names = ["post"]

    def post(self, request, invoice_pk: int):
        invoice = get_object_or_404(StaffInvoice, pk=invoice_pk,
                                    status=StaffInvoice.PaymentStatus.PENDING)
        receipt = request.FILES.get("bank_receipt")
        if not receipt:
            messages.error(request, "فایل فیش بانکی الزامی است.")
            return redirect("payroll:staff-invoice-list")

        err = _validate_image(receipt)
        if err:
            messages.error(request, err)
            return redirect("payroll:staff-invoice-list")

        compressed = _compress_image(receipt)
        invoice.bank_receipt.save(
            compressed.name if compressed else receipt.name,
            compressed or receipt, save=False
        )
        invoice.status  = StaffInvoice.PaymentStatus.PAID
        invoice.paid_at = timezone.now()
        invoice.save(update_fields=["bank_receipt", "status", "paid_at"])

        # اعلان به گیرنده با لینک تأیید
        from django.urls import reverse
        confirm_url = request.build_absolute_uri(
            reverse("payroll:staff-invoice-confirm", args=[invoice.pk])
        )
        Notification.objects.create(
            recipient=invoice.recipient,
            type=Notification.NotificationType.SALARY_PAID,
            title=f"💰 فیش پرداخت «{invoice.title}» آماده تأیید",
            message=(
                f"مبلغ {invoice.amount:,.0f} ریال بابت «{invoice.title}» پرداخت شد. "
                f"لطفاً دریافت را تأیید کنید: {confirm_url}"
            ),
        )
        messages.success(request, f"فیش پرداخت بارگذاری و برای {invoice.recipient.get_full_name()} ارسال شد.")
        return redirect("payroll:staff-invoice-list")


class RecipientConfirmInvoiceView(LoginRequiredMixin, View):
    """گیرنده فیش پرداخت را تأیید می‌کند"""
    template_name = "payroll/staff_invoice_confirm.html"

    def get(self, request, invoice_pk: int):
        invoice = get_object_or_404(StaffInvoice, pk=invoice_pk, recipient=request.user)
        return render(request, self.template_name, {"invoice": invoice})

    def post(self, request, invoice_pk: int):
        invoice = get_object_or_404(StaffInvoice, pk=invoice_pk, recipient=request.user)
        action  = request.POST.get("action", "")

        if action == "confirm" and invoice.status == StaffInvoice.PaymentStatus.PAID:
            invoice.status                 = StaffInvoice.PaymentStatus.CONFIRMED
            invoice.recipient_confirmed    = True
            invoice.recipient_confirmed_at = timezone.now()
            invoice.save(update_fields=["status", "recipient_confirmed", "recipient_confirmed_at"])

            FinancialTransaction.objects.get_or_create(
                user=request.user,
                tx_type=FinancialTransaction.TxType.STAFF_INVOICE_PAID,
                staff_invoice=invoice,
                defaults={
                    "direction":    FinancialTransaction.Direction.CREDIT,
                    "amount":       invoice.amount,
                    "description":  invoice.title,
                    "performed_by": request.user,
                },
            )
            for fm in CustomUser.objects.filter(is_finance_manager=True, is_active=True):
                Notification.objects.create(
                    recipient=fm,
                    type=Notification.NotificationType.GENERAL,
                    title=f"✅ {request.user.get_full_name()} پرداخت «{invoice.title}» را تأیید کرد",
                    message=f"مبلغ {invoice.amount:,.0f} ریال تأیید دریافت شد.",
                )
            messages.success(request, "دریافت پرداخت با موفقیت تأیید شد.")

        elif action == "dispute":
            note = request.POST.get("note", "").strip()
            for fm in CustomUser.objects.filter(is_finance_manager=True, is_active=True):
                Notification.objects.create(
                    recipient=fm,
                    type=Notification.NotificationType.GENERAL,
                    title=f"⚠️ اعتراض به فاکتور «{invoice.title}»",
                    message=f"کاربر {request.user.get_full_name()} اعتراض دارد. "
                            + (f"توضیح: {note}" if note else ""),
                )
            messages.warning(request, "اعتراض شما ثبت و به مدیر مالی اطلاع داده شد.")

        return redirect("payroll:my-financial-history")


class StaffInvoiceCancelView(FinanceOnlyMixin, View):
    http_method_names = ["post"]

    def post(self, request, invoice_pk: int):
        invoice = get_object_or_404(StaffInvoice, pk=invoice_pk,
                                    status=StaffInvoice.PaymentStatus.PENDING)
        invoice.status = StaffInvoice.PaymentStatus.CANCELED
        invoice.save(update_fields=["status"])
        messages.success(request, f"فاکتور «{invoice.title}» لغو شد.")
        return redirect("payroll:staff-invoice-list")


# ═══════════════════════════════════════════════════════════════════
#  6. تاریخچه مالی
# ═══════════════════════════════════════════════════════════════════

class MyFinancialHistoryView(LoginRequiredMixin, ListView):
    """تاریخچه مالی شخصی — برای همه کاربران"""
    template_name       = "payroll/my_financial_history.html"
    context_object_name = "transactions"
    paginate_by         = 25

    def get_queryset(self):
        return FinancialTransaction.objects.filter(
            user=self.request.user
        ).select_related(
            "player_invoice__category",
            "coach_salary__category",
            "staff_invoice",
            "performed_by",
        ).order_by("-created_at")

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        qs  = self.get_queryset()

        ctx["total_debit"]  = qs.filter(direction="debit").aggregate(s=Sum("amount"))["s"] or 0
        ctx["total_credit"] = qs.filter(direction="credit").aggregate(s=Sum("amount"))["s"] or 0

        # فاکتورهای معوق (بازیکن)
        ctx["pending_invoices"] = PlayerInvoice.objects.filter(
            player__user=self.request.user,
            status__in=["pending", "debtor"],
        ).order_by("-jalali_year", "-jalali_month")

        # حقوق‌های در انتظار تأیید (مربی)
        ctx["salary_to_confirm"] = CoachSalary.objects.filter(
            coach__user=self.request.user,
            status=CoachSalary.SalaryStatus.PAID,
        ).select_related("category", "attendance_sheet")

        # فاکتورهای دستی در انتظار تأیید (همه کاربران)
        ctx["invoice_to_confirm"] = StaffInvoice.objects.filter(
            recipient=self.request.user,
            status=StaffInvoice.PaymentStatus.PAID,
        )

        # حقوق در انتظار تأیید (مربی) — برای template
        ctx["pending_salaries"]       = ctx["salary_to_confirm"]
        ctx["pending_salary_count"]   = ctx["salary_to_confirm"].count()
        ctx["pending_staff_invoices"] = ctx["invoice_to_confirm"]

        # فیش‌های حقوق تأیید شده (مربی)
        ctx["confirmed_salaries"] = CoachSalary.objects.filter(
            coach__user=self.request.user,
            status=CoachSalary.SalaryStatus.CONFIRMED,
        ).select_related("category", "attendance_sheet").order_by(
            "-attendance_sheet__jalali_year", "-attendance_sheet__jalali_month"
        )[:8]

        # فاکتورهای دستی تأیید شده
        ctx["confirmed_staff_invoices"] = StaffInvoice.objects.filter(
            recipient=self.request.user,
            status=StaffInvoice.PaymentStatus.CONFIRMED,
        ).order_by("-created_at")[:8]

        return ctx


class FinanceAllHistoryView(FinanceAccessMixin, ListView):
    """تاریخچه مالی کل سیستم"""
    template_name       = "payroll/finance_all_history.html"
    context_object_name = "transactions"
    paginate_by         = 40

    def get_queryset(self):
        qs = FinancialTransaction.objects.select_related(
            "user", "performed_by",
            "player_invoice__category",
            "coach_salary__category",
            "staff_invoice",
        ).order_by("-created_at")
        tx  = self.request.GET.get("tx_type", "")
        uid = self.request.GET.get("user_id", "")
        if tx:
            qs = qs.filter(tx_type=tx)
        if uid:
            qs = qs.filter(user_id=uid)
        return qs

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx.update({
            "tx_type_choices": FinancialTransaction.TxType.choices,
            "tx_type_filter":  self.request.GET.get("tx_type", ""),
            "user_filter":     self.request.GET.get("user_id", ""),
            "users":           CustomUser.objects.filter(is_active=True).order_by("last_name"),
        })
        return ctx


# ═══════════════════════════════════════════════════════════════════
#  7. هزینه‌ها و درآمد (با فیلتر بازه شمسی)
# ═══════════════════════════════════════════════════════════════════

class ExpenseListView(FinanceAccessMixin, ListView):
    """لیست هزینه‌ها و درآمدها با فیلتر پیشرفته"""
    template_name       = "payroll/expense_list.html"
    context_object_name = "expenses"
    paginate_by         = 30

    def _parse_jalali_to_date(self, jstr: str):
        """تبدیل رشته 'YYYY/MM/DD' شمسی به date میلادی"""
        try:
            parts = jstr.replace("-", "/").split("/")
            jd    = jdatetime.date(int(parts[0]), int(parts[1]), int(parts[2]))
            return jd.togregorian()
        except Exception:
            return None

    def get_queryset(self):
        qs   = Expense.objects.select_related("category", "recorded_by").order_by("-date", "-created_at")
        q    = self.request.GET.get("q", "").strip()
        cat  = self.request.GET.get("cat", "")
        kind = self.request.GET.get("kind", "")
        d_from = self.request.GET.get("date_from", "").strip()
        d_to   = self.request.GET.get("date_to", "").strip()

        if q:
            qs = qs.filter(Q(title__icontains=q) | Q(description__icontains=q))
        if cat:
            qs = qs.filter(category__pk=cat)
        if kind:
            qs = qs.filter(transaction_type=kind)
        if d_from:
            gd = self._parse_jalali_to_date(d_from)
            if gd:
                qs = qs.filter(date__gte=gd)
        if d_to:
            gd = self._parse_jalali_to_date(d_to)
            if gd:
                qs = qs.filter(date__lte=gd)
        return qs

    def get_context_data(self, **kwargs):
        ctx  = super().get_context_data(**kwargs)
        base = self.get_queryset()
        ctx.update({
            "q":            self.request.GET.get("q", ""),
            "cat_filter":   self.request.GET.get("cat", ""),
            "kind_filter":  self.request.GET.get("kind", ""),
            "date_from":    self.request.GET.get("date_from", ""),
            "date_to":      self.request.GET.get("date_to", ""),
            "categories":   ExpenseCategory.objects.filter(is_active=True),
            "total_expense": base.filter(transaction_type="expense").aggregate(s=Sum("amount"))["s"] or 0,
            "total_income":  base.filter(transaction_type="income").aggregate(s=Sum("amount"))["s"] or 0,
            "balance":       (base.filter(transaction_type="income").aggregate(s=Sum("amount"))["s"] or 0) -
                             (base.filter(transaction_type="expense").aggregate(s=Sum("amount"))["s"] or 0),
        })

        # تفکیک بر اساس دسته‌بندی (category breakdown)
        from django.db.models import Case, When, DecimalField as DField
        cats = ExpenseCategory.objects.filter(is_active=True)
        breakdown = []
        for cat in cats:
            cat_qs = base.filter(category=cat)
            cat_exp = cat_qs.filter(transaction_type="expense").aggregate(s=Sum("amount"))["s"] or 0
            cat_inc = cat_qs.filter(transaction_type="income").aggregate(s=Sum("amount"))["s"] or 0
            if cat_exp > 0 or cat_inc > 0:
                breakdown.append({
                    "name":    cat.name,
                    "expense": cat_exp,
                    "income":  cat_inc,
                    "net":     cat_inc - cat_exp,
                })
        ctx["cat_breakdown"] = sorted(breakdown, key=lambda x: abs(x["net"]), reverse=True)
        return ctx


class ExpenseCreateView(FinanceAccessMixin, View):
    """ثبت هزینه/درآمد جدید با آپلود تصویر رسید"""
    template_name = "payroll/expense_form.html"

    def get(self, request):
        categories = ExpenseCategory.objects.filter(is_active=True)
        return render(request, self.template_name, {
            "categories":     categories,
            "has_categories": categories.exists(),
        })

    def post(self, request):
        from django.core.files.base import ContentFile
        categories = ExpenseCategory.objects.filter(is_active=True)
        try:
            cat    = ExpenseCategory.objects.get(pk=request.POST["category"])
            title  = request.POST["title"].strip()
            amount = Decimal(request.POST["amount"])
            kind   = request.POST.get("transaction_type", "expense")
            desc   = request.POST.get("description", "").strip()
            # تاریخ شمسی
            d_str  = request.POST.get("date_jalali", "").strip()
            parts  = d_str.replace("-", "/").split("/")
            jd     = jdatetime.date(int(parts[0]), int(parts[1]), int(parts[2]))
            gr_date= jd.togregorian()
        except Exception as e:
            return render(request, self.template_name, {
                "categories": categories,
                "prev": request.POST,
                "has_categories": categories.exists(),
                "error": str(e),
            })

        expense = Expense(
            category=cat, title=title, amount=amount,
            transaction_type=kind, date=gr_date,
            description=desc, recorded_by=request.user,
        )

        # آپلود و فشرده‌سازی تصویر رسید
        receipt = request.FILES.get("receipt_image")
        if receipt:
            err = _validate_image(receipt)
            if err:
                messages.error(request, err)
                return render(request, self.template_name, {
                    "categories": categories, "prev": request.POST,
                    "has_categories": categories.exists(),
                })
            compressed = _compress_image(receipt)
            expense.receipt_image.save(
                compressed.name if compressed else receipt.name,
                compressed or receipt, save=False
            )

        expense.save()
        messages.success(request,
            f"{'هزینه' if kind=='expense' else 'درآمد'} «{title}» ثبت شد.")
        return redirect("payroll:expense-list")


class ExpenseCategoryCreateView(FinanceAccessMixin, View):
    template_name = "payroll/expense_category_form.html"

    def get(self, request):
        return render(request, self.template_name, {})

    def post(self, request):
        name = request.POST.get("name", "").strip()
        if not name:
            messages.error(request, "نام دسته الزامی است.")
            return render(request, self.template_name, {})
        ExpenseCategory.objects.create(
            name=name,
            description=request.POST.get("description", "").strip(),
            created_by=request.user,
        )
        messages.success(request, f"دسته «{name}» ایجاد شد.")
        return redirect("payroll:expense-list")


class ExpenseCategoryListView(FinanceAccessMixin, ListView):
    template_name       = "payroll/expense_category_list.html"
    context_object_name = "categories"

    def get_queryset(self):
        return ExpenseCategory.objects.order_by("name")


# ═══════════════════════════════════════════════════════════════════
#  تعیین نرخ مربیان
# ═══════════════════════════════════════════════════════════════════

class CoachRateManageView(FinanceOnlyMixin, TemplateView):
    template_name = "payroll/coach_rate_manage.html"

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx.update({
            "categories": TrainingCategory.objects.filter(is_active=True).prefetch_related(
                "coach_rates__coach"
            ).order_by("name"),
            "coaches": Coach.objects.filter(is_active=True).select_related("user").order_by("last_name"),
            "rates":   CoachCategoryRate.objects.select_related("coach", "category").order_by(
                "category__name", "coach__last_name"
            ),
        })
        return ctx

    def post(self, request):
        coach_pk    = request.POST.get("coach_id", "")
        category_pk = request.POST.get("category_id", "")
        try:
            rate = Decimal(request.POST.get("session_rate", "0"))
            coach    = Coach.objects.get(pk=coach_pk)
            category = TrainingCategory.objects.get(pk=category_pk)
        except Exception as e:
            messages.error(request, f"خطا: {e}")
            return redirect("payroll:coach-rate-manage")

        obj, created = CoachCategoryRate.objects.update_or_create(
            coach=coach, category=category,
            defaults={"session_rate": rate, "is_active": True},
        )
        messages.success(request,
            f"نرخ {coach} در {category}: {rate:,.0f} ریال/جلسه "
            f"({'ایجاد' if created else 'به‌روز'} شد).")
        return redirect("payroll:coach-rate-manage")