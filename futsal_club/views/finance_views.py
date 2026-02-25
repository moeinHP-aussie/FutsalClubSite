"""
futsal_club/views/finance_views.py
────────────────────────────────────────────────────────────────────
ویوهای تکمیلی پنل مدیریت مالی:
  - StaffInvoice  : فاکتور دستی برای اعضاء باشگاه
  - FinancialHistory: تاریخچه مالی هر کاربر
  - AttendanceReadOnly: مشاهده فرم حضورغیاب توسط مدیر مالی
"""

from __future__ import annotations

import logging
from decimal import Decimal

import jdatetime
from django.contrib import messages
from django.contrib.auth.mixins import LoginRequiredMixin
from django.http import Http404, JsonResponse
from django.shortcuts import get_object_or_404, redirect
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
    FinancialTransaction,
    Notification,
    PlayerInvoice,
    StaffInvoice,
    TrainingCategory,
)
from ..services.jalali_utils import JalaliMonth, parse_jalali_month_from_request

logger = logging.getLogger(__name__)


# ────────────────────────────────────────────────────────────────────
#  Mixins
# ────────────────────────────────────────────────────────────────────

class FinanceAccessMixin(LoginRequiredMixin, RoleRequiredMixin):
    allowed_roles = ["is_finance_manager", "is_technical_director", "is_superuser"]


class FinanceOnlyMixin(LoginRequiredMixin, RoleRequiredMixin):
    allowed_roles = ["is_finance_manager", "is_superuser"]


# ────────────────────────────────────────────────────────────────────
#  1. StaffInvoice — فاکتور دستی برای اعضاء
# ────────────────────────────────────────────────────────────────────

class StaffInvoiceListView(FinanceOnlyMixin, ListView):
    """
    لیست تمام فاکتورهای دستی با قابلیت فیلتر.
    """
    template_name     = "payroll/staff_invoice_list.html"
    context_object_name = "invoices"
    paginate_by       = 30

    def get_queryset(self):
        qs = StaffInvoice.objects.select_related("recipient", "created_by")
        status = self.request.GET.get("status", "")
        if status:
            qs = qs.filter(status=status)
        recipient = self.request.GET.get("recipient", "").strip()
        if recipient:
            qs = qs.filter(
                recipient__username__icontains=recipient
            ) | qs.filter(
                recipient__first_name__icontains=recipient
            ) | qs.filter(
                recipient__last_name__icontains=recipient
            )
        return qs.order_by("-created_at")

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx["status_filter"]   = self.request.GET.get("status", "")
        ctx["recipient_filter"]= self.request.GET.get("recipient", "")
        ctx["status_choices"]  = StaffInvoice.PaymentStatus.choices
        ctx["total_pending"]   = StaffInvoice.objects.filter(status="pending").count()
        ctx["total_paid"]      = StaffInvoice.objects.filter(status="paid").count()
        ctx["users_list"]      = CustomUser.objects.filter(is_active=True).order_by("last_name")
        return ctx


class StaffInvoiceCreateView(FinanceOnlyMixin, View):
    """
    ایجاد فاکتور دستی برای یک عضو باشگاه.
    POST: recipient_id, title, description, amount
    """
    template_name = "payroll/staff_invoice_create.html"

    def get(self, request):
        from django.shortcuts import render
        users = CustomUser.objects.filter(is_active=True).order_by("last_name", "first_name")
        return render(request, self.template_name, {"users": users})

    def post(self, request):
        recipient_id = request.POST.get("recipient_id", "").strip()
        title        = request.POST.get("title", "").strip()
        description  = request.POST.get("description", "").strip()
        amount_raw   = request.POST.get("amount", "0").replace(",", "").strip()

        errors = {}
        if not recipient_id:
            errors["recipient"] = "دریافت‌کننده الزامی است."
        if not title:
            errors["title"] = "عنوان الزامی است."
        try:
            amount = Decimal(amount_raw)
            if amount <= 0:
                raise ValueError
        except (ValueError, Exception):
            errors["amount"] = "مبلغ باید یک عدد مثبت باشد."

        if errors:
            from django.shortcuts import render
            users = CustomUser.objects.filter(is_active=True).order_by("last_name")
            return render(request, self.template_name, {
                "users": users, "errors": errors,
                "prev": request.POST,
            })

        recipient = get_object_or_404(CustomUser, pk=recipient_id, is_active=True)
        invoice = StaffInvoice.objects.create(
            recipient=recipient,
            title=title,
            description=description,
            amount=amount,
            status=StaffInvoice.PaymentStatus.PENDING,
            created_by=request.user,
        )

        # اعلان به کاربر مقصد
        Notification.objects.create(
            recipient=recipient,
            type=Notification.NotificationType.STAFF_INVOICE,
            title=f"فاکتور جدید: {title}",
            message=(
                f"یک فاکتور به مبلغ {amount:,.0f} ریال "
                f"با عنوان «{title}» برای شما صادر شده است. "
                "لطفاً جهت پرداخت اقدام نمایید."
            ),
        )

        # ثبت در تاریخچه مالی
        FinancialTransaction.objects.create(
            user=recipient,
            tx_type=FinancialTransaction.TxType.STAFF_INVOICE,
            direction=FinancialTransaction.Direction.DEBIT,
            amount=amount,
            description=f"فاکتور دستی: {title}",
            staff_invoice=invoice,
            performed_by=request.user,
        )

        messages.success(request, f"فاکتور «{title}» برای {recipient.get_full_name()} صادر شد.")
        return redirect("payroll:staff-invoice-list")


class StaffInvoiceMarkPaidView(FinanceOnlyMixin, View):
    """
    تأیید پرداخت فاکتور دستی توسط مدیر مالی.
    POST با ref_id (شماره مرجع پرداخت)
    """
    def post(self, request, invoice_pk: int):
        invoice = get_object_or_404(StaffInvoice, pk=invoice_pk)
        if invoice.status != StaffInvoice.PaymentStatus.PENDING:
            messages.warning(request, "این فاکتور قبلاً پردازش شده.")
            return redirect("payroll:staff-invoice-list")

        ref_id = request.POST.get("ref_id", "").strip()
        invoice.status           = StaffInvoice.PaymentStatus.PAID
        invoice.paid_at          = timezone.now()
        invoice.zarinpal_ref_id  = ref_id
        invoice.save(update_fields=["status", "paid_at", "zarinpal_ref_id"])

        # اعلان به کاربر
        Notification.objects.create(
            recipient=invoice.recipient,
            type=Notification.NotificationType.INVOICE_PAID,
            title=f"پرداخت تأیید شد: {invoice.title}",
            message=(
                f"پرداخت فاکتور «{invoice.title}» "
                f"به مبلغ {invoice.amount:,.0f} ریال تأیید شد."
                + (f" شماره مرجع: {ref_id}" if ref_id else "")
            ),
        )

        # ثبت در تاریخچه مالی
        FinancialTransaction.objects.get_or_create(
            user=invoice.recipient,
            tx_type=FinancialTransaction.TxType.STAFF_INVOICE_PAID,
            staff_invoice=invoice,
            defaults={
                "direction": FinancialTransaction.Direction.DEBIT,
                "amount": invoice.amount,
                "description": f"پرداخت فاکتور: {invoice.title}",
                "performed_by": request.user,
            },
        )

        messages.success(request, f"فاکتور «{invoice.title}» تأیید پرداخت شد.")
        return redirect("payroll:staff-invoice-list")


class StaffInvoiceCancelView(FinanceOnlyMixin, View):
    """لغو فاکتور دستی."""
    def post(self, request, invoice_pk: int):
        invoice = get_object_or_404(StaffInvoice, pk=invoice_pk, status="pending")
        invoice.status = StaffInvoice.PaymentStatus.CANCELED
        invoice.save(update_fields=["status"])
        messages.success(request, f"فاکتور «{invoice.title}» لغو شد.")
        return redirect("payroll:staff-invoice-list")


# ────────────────────────────────────────────────────────────────────
#  2. FinancialHistory — تاریخچه مالی برای همه کاربران
# ────────────────────────────────────────────────────────────────────

class MyFinancialHistoryView(LoginRequiredMixin, ListView):
    """
    تاریخچه مالی شخصی هر کاربر — قابل دسترس برای همه.
    هر کاربر فقط تاریخچه خودش را می‌بینه.
    """
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

        total_debit  = sum(t.amount for t in qs if t.direction == "debit")
        total_credit = sum(t.amount for t in qs if t.direction == "credit")

        ctx["total_debit"]   = total_debit
        ctx["total_credit"]  = total_credit
        ctx["user_invoices"] = PlayerInvoice.objects.filter(
            player__user=self.request.user
        ).order_by("-jalali_year", "-jalali_month")[:5]
        ctx["pending_invoices"] = PlayerInvoice.objects.filter(
            player__user=self.request.user,
            status__in=["pending", "debtor"],
        ).order_by("-jalali_year", "-jalali_month")
        ctx["staff_invoices"] = StaffInvoice.objects.filter(
            recipient=self.request.user,
        ).order_by("-created_at")[:5]
        return ctx


class FinanceAllHistoryView(FinanceAccessMixin, ListView):
    """
    مشاهده تاریخچه مالی همه کاربران توسط مدیر مالی/مدیر فنی.
    """
    template_name       = "payroll/finance_all_history.html"
    context_object_name = "transactions"
    paginate_by         = 40

    def get_queryset(self):
        qs = FinancialTransaction.objects.select_related(
            "user",
            "player_invoice__category",
            "coach_salary__category",
            "staff_invoice",
            "performed_by",
        )
        tx_type = self.request.GET.get("tx_type", "")
        if tx_type:
            qs = qs.filter(tx_type=tx_type)
        user_id = self.request.GET.get("user_id", "")
        if user_id:
            qs = qs.filter(user_id=user_id)
        return qs.order_by("-created_at")

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx["tx_type_filter"] = self.request.GET.get("tx_type", "")
        ctx["user_filter"]    = self.request.GET.get("user_id", "")
        ctx["tx_type_choices"]= FinancialTransaction.TxType.choices
        ctx["users"]          = CustomUser.objects.filter(is_active=True).order_by("last_name")
        return ctx


# ────────────────────────────────────────────────────────────────────
#  3. PlayerInvoiceStatusUpdate — تعیین وضعیت شهریه توسط مدیر مالی
# ────────────────────────────────────────────────────────────────────

class InvoiceStatusUpdateView(FinanceOnlyMixin, View):
    """
    مدیر مالی وضعیت فاکتور را تغییر می‌دهد.
    POST: invoice_pk, new_status, notes
    وضعیت‌های مجاز: pending → paid | debtor | pending_confirm
    """
    def post(self, request, invoice_pk: int):
        invoice    = get_object_or_404(PlayerInvoice, pk=invoice_pk)
        new_status = request.POST.get("new_status", "").strip()
        notes      = request.POST.get("notes", "").strip()

        VALID = ["paid", "debtor", "pending", "pending_confirm"]
        if new_status not in VALID:
            messages.error(request, "وضعیت نامعتبر.")
            return redirect(request.META.get("HTTP_REFERER", "payroll:finance-dashboard"))

        old_status = invoice.status
        invoice.status = new_status
        if notes:
            invoice.notes = notes
        if new_status == "paid" and old_status != "paid":
            invoice.paid_at      = timezone.now()
            invoice.confirmed_by = request.user
        invoice.save()

        # اعلان به بازیکن
        player = invoice.player
        if player.user:
            month_str = f"{invoice.jalali_year}/{invoice.jalali_month:02d}"
            notif_map = {
                "paid":    ("✅ شهریه تأیید شد", f"شهریه {month_str} پرداخت‌شده تأیید شد."),
                "debtor":  ("⚠️ شهریه معوق", f"شهریه {month_str} دسته «{invoice.category.name}» به‌عنوان معوق ثبت شد."),
                "pending": ("🔄 شهریه در انتظار", f"وضعیت شهریه {month_str} به «در انتظار» تغییر کرد."),
                "pending_confirm": ("📋 رسید در انتظار تأیید", f"رسید شهریه {month_str} دریافت شد و در انتظار تأیید است."),
            }
            title, msg = notif_map.get(new_status, ("وضعیت شهریه", "وضعیت شهریه شما تغییر کرد."))
            Notification.objects.create(
                recipient=player.user,
                type=Notification.NotificationType.INVOICE_PAID if new_status == "paid" else Notification.NotificationType.INVOICE_DUE,
                title=title,
                message=msg + (f"\n یادداشت: {notes}" if notes else ""),
                related_player=player,
            )

            # ثبت در تاریخچه مالی فقط برای پرداخت
            if new_status == "paid" and old_status != "paid":
                FinancialTransaction.objects.get_or_create(
                    user=player.user,
                    tx_type=FinancialTransaction.TxType.INVOICE_PAID,
                    player_invoice=invoice,
                    defaults={
                        "direction": FinancialTransaction.Direction.DEBIT,
                        "amount": invoice.final_amount,
                        "description": f"پرداخت شهریه «{invoice.category.name}» — {month_str}",
                        "performed_by": request.user,
                    },
                )

        status_label = dict(PlayerInvoice.PaymentStatus.choices).get(new_status, new_status)
        messages.success(
            request,
            f"وضعیت فاکتور {player.first_name} {player.last_name} به «{status_label}» تغییر کرد."
        )
        return redirect(request.META.get("HTTP_REFERER", "payroll:finance-dashboard"))


class BulkInvoiceStatusView(FinanceOnlyMixin, View):
    """
    تغییر دسته‌ای وضعیت فاکتورهای یک دسته آموزشی.
    POST: category_pk, year, month, new_status, invoice_ids[] (اختیاری)
    """
    def post(self, request):
        category_pk = request.POST.get("category_pk")
        year        = request.POST.get("year", "")
        month_      = request.POST.get("month", "")
        new_status  = request.POST.get("new_status", "").strip()
        invoice_ids = request.POST.getlist("invoice_ids[]")

        VALID = ["paid", "debtor", "pending"]
        if new_status not in VALID:
            messages.error(request, "وضعیت نامعتبر.")
            return redirect("payroll:finance-dashboard")

        try:
            y, m = int(year), int(month_)
        except (ValueError, TypeError):
            messages.error(request, "ماه یا سال نامعتبر.")
            return redirect("payroll:finance-dashboard")

        qs = PlayerInvoice.objects.filter(jalali_year=y, jalali_month=m)
        if category_pk:
            qs = qs.filter(category_id=category_pk)
        if invoice_ids:
            qs = qs.filter(pk__in=[int(i) for i in invoice_ids if i.isdigit()])

        count = 0
        for invoice in qs.select_related("player__user", "category"):
            if invoice.status == new_status:
                continue
            old_status     = invoice.status
            invoice.status = new_status
            if new_status == "paid" and old_status != "paid":
                invoice.paid_at      = timezone.now()
                invoice.confirmed_by = request.user
            invoice.save(update_fields=["status", "paid_at", "confirmed_by"] if new_status == "paid" else ["status"])
            count += 1

            if invoice.player.user:
                month_str = f"{y}/{m:02d}"
                Notification.objects.create(
                    recipient=invoice.player.user,
                    type=Notification.NotificationType.INVOICE_PAID if new_status == "paid" else Notification.NotificationType.INVOICE_DUE,
                    title="وضعیت شهریه تغییر کرد",
                    message=f"وضعیت شهریه {month_str} دسته «{invoice.category.name}» به «{dict(PlayerInvoice.PaymentStatus.choices)[new_status]}» تغییر کرد.",
                    related_player=invoice.player,
                )

        messages.success(request, f"{count} فاکتور به‌روز شد.")
        if category_pk:
            return redirect("payroll:invoice-list", category_pk=category_pk)
        return redirect("payroll:finance-dashboard")


# ────────────────────────────────────────────────────────────────────
#  4. AttendanceReadOnly — مشاهده فرم حضورغیاب توسط مدیر مالی
# ────────────────────────────────────────────────────────────────────

class FinanceAttendanceCategoryListView(FinanceAccessMixin, ListView):
    """
    مدیر مالی لیست دسته‌ها را می‌بینه تا فرم‌های حضور مربوط به آنها رو مشاهده کنه.
    """
    template_name       = "payroll/finance_attendance_cats.html"
    context_object_name = "categories"

    def get_queryset(self):
        return TrainingCategory.objects.filter(is_active=True).order_by("name")


class FinanceAttendanceSheetView(FinanceAccessMixin, TemplateView):
    """
    مشاهده فقط‌خواندنی لیست جلسات یک دسته — برای مدیر مالی.
    فقط نمایش، بدون امکان ثبت یا ویرایش.
    """
    template_name = "payroll/finance_attendance_sheet.html"

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        cat = get_object_or_404(TrainingCategory, pk=self.kwargs["category_pk"])
        sheets = AttendanceSheet.objects.filter(
            category=cat
        ).prefetch_related(
            "sessions__attendances__player"
        ).order_by("-jalali_year", "-jalali_month")

        ctx["category"] = cat
        ctx["sheets"]   = sheets
        ctx["read_only"]= True  # نشانه فقط‌خواندنی
        return ctx


class FinanceAttendanceSessionView(FinanceAccessMixin, TemplateView):
    """
    مشاهده جزئیات یک جلسه — فقط‌خواندنی برای مدیر مالی.
    """
    template_name = "payroll/finance_session_detail.html"

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        from ..models import SessionDate, PlayerAttendance
        session = get_object_or_404(
            SessionDate, pk=self.kwargs["session_pk"]
        )
        attendances = PlayerAttendance.objects.filter(
            session=session
        ).select_related("player").order_by("player__last_name")

        ctx["session"]     = session
        ctx["attendances"] = attendances
        ctx["category"]    = session.sheet.category
        ctx["read_only"]   = True
        return ctx


# ────────────────────────────────────────────────────────────────────
#  5. FinanceDashboard — داشبورد جامع مالی (نسخه بهبودیافته)
# ────────────────────────────────────────────────────────────────────

class FinanceDashboardV2View(FinanceAccessMixin, TemplateView):
    """
    داشبورد مالی جامع — نسخه بهبودیافته v2
    - خلاصه ماه جاری
    - فاکتورهای در انتظار تأیید
    - حقوق‌های تأییدنشده
    - فاکتورهای دستی معلق
    - آمار درآمد/هزینه
    """
    template_name = "payroll/finance_dashboard_v2.html"

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        today = jdatetime.date.today()

        # فیلتر ماه
        try:
            y = int(self.request.GET.get("year", today.year))
            m = int(self.request.GET.get("month", today.month))
        except (ValueError, TypeError):
            y, m = today.year, today.month

        month = JalaliMonth(y, m)
        ctx["month"]      = month
        ctx["prev_month"] = month.prev_month
        ctx["next_month"] = month.next_month

        # ── آمار فاکتورهای شهریه ──────────────────────────────────
        invoices = PlayerInvoice.objects.filter(jalali_year=y, jalali_month=m)
        inv_paid    = invoices.filter(status="paid")
        inv_pending = invoices.filter(status="pending")
        inv_debtor  = invoices.filter(status="debtor")
        inv_confirm = invoices.filter(status="pending_confirm")

        ctx["invoice_stats"] = {
            "total":         invoices.count(),
            "paid":          inv_paid.count(),
            "pending":       inv_pending.count(),
            "debtor":        inv_debtor.count(),
            "pending_confirm": inv_confirm.count(),
            "paid_amount":   sum(i.final_amount for i in inv_paid),
            "pending_amount":sum(i.final_amount for i in inv_pending) + sum(i.final_amount for i in inv_debtor),
        }

        # ── آمار حقوق مربیان ──────────────────────────────────────
        salaries = CoachSalary.objects.filter(
            attendance_sheet__jalali_year=y,
            attendance_sheet__jalali_month=m,
        )
        ctx["salary_stats"] = {
            "total":     salaries.count(),
            "calculated":salaries.filter(status="calculated").count(),
            "approved":  salaries.filter(status="approved").count(),
            "paid":      salaries.filter(status="paid").count(),
            "total_amount": sum(s.final_amount for s in salaries.filter(status__in=["approved","paid"])),
        }

        # ── فاکتورهای دستی ────────────────────────────────────────
        staff_pending = StaffInvoice.objects.filter(status="pending")
        ctx["staff_invoice_stats"] = {
            "pending_count":  staff_pending.count(),
            "pending_amount": sum(i.amount for i in staff_pending),
        }

        # ── فاکتورهایی که نیاز به تأیید دارند ────────────────────
        ctx["awaiting_confirm"] = PlayerInvoice.objects.filter(
            status="pending_confirm"
        ).select_related("player", "category")[:10]

        # ── فاکتورهای بدهکار ──────────────────────────────────────
        ctx["debtor_invoices"] = PlayerInvoice.objects.filter(
            status="debtor"
        ).select_related("player", "category").order_by("-jalali_year", "-jalali_month")[:10]

        # ── دسته‌های آموزشی ───────────────────────────────────────
        ctx["categories"] = TrainingCategory.objects.filter(is_active=True).order_by("name")

        # ── حقوق‌های تأیید‌شده هنوز پرداخت‌نشده ──────────────────
        ctx["approved_salaries"] = CoachSalary.objects.filter(
            status="approved"
        ).select_related("coach", "category", "attendance_sheet").order_by("-created_at")[:10]

        return ctx


# ══════════════════════════════════════════════════════════════════════
#  تعیین نرخ مربیان به ازای هر دسته — فقط مدیر مالی
# ══════════════════════════════════════════════════════════════════════

class CoachRateManageView(FinanceOnlyMixin, TemplateView):
    """
    مدیر مالی نرخ دریافتی هر مربی را برای هر دسته آموزشی تعیین می‌کند.
    GET  → جدول نرخ‌ها
    POST → ذخیره/به‌روزرسانی نرخ‌ها
    """
    template_name = "payroll/coach_rate_manage.html"

    def get_context_data(self, **kwargs):
        ctx        = super().get_context_data(**kwargs)
        categories = TrainingCategory.objects.filter(is_active=True).order_by("name")
        coaches    = Coach.objects.filter(is_active=True).select_related("user").order_by("last_name")

        # ساخت ساختار نرخ‌ها برای render آسان در template:
        # coach_rates[coach_pk][category_pk] = session_rate
        coach_rates = {}
        for r in CoachCategoryRate.objects.select_related("coach", "category"):
            if r.coach_id not in coach_rates:
                coach_rates[r.coach_id] = {}
            coach_rates[r.coach_id][r.category_id] = int(r.session_rate)

        # برای هر مربی و دسته، نرخ فعلی را می‌فرستیم
        coaches_with_rates = []
        for coach in coaches:
            cat_rates = []
            for cat in categories:
                rate_val = coach_rates.get(coach.pk, {}).get(cat.pk, "")
                cat_rates.append({
                    "category":   cat,
                    "field_name": f"rate_{coach.pk}_{cat.pk}",
                    "value":      rate_val,
                })
            coaches_with_rates.append({
                "coach":     coach,
                "cat_rates": cat_rates,
            })

        ctx["categories"]          = categories
        ctx["coaches_with_rates"]  = coaches_with_rates
        return ctx

    def post(self, request):
        saved   = 0
        removed = 0

        for key, value in request.POST.items():
            # کلیدها به شکل rate_<coach_pk>_<category_pk>
            if not key.startswith("rate_"):
                continue
            parts = key.split("_")
            if len(parts) != 3:
                continue
            try:
                coach_pk    = int(parts[1])
                category_pk = int(parts[2])
                amount      = value.strip()
            except (ValueError, IndexError):
                continue

            try:
                coach    = Coach.objects.get(pk=coach_pk)
                category = TrainingCategory.objects.get(pk=category_pk)
            except (Coach.DoesNotExist, TrainingCategory.DoesNotExist):
                continue

            if amount == "" or amount == "0":
                # حذف نرخ اگر خالی شد
                deleted, _ = CoachCategoryRate.objects.filter(
                    coach=coach, category=category
                ).delete()
                if deleted:
                    removed += 1
            else:
                try:
                    rate_val = int(amount)
                    if rate_val < 0:
                        continue
                    obj, created = CoachCategoryRate.objects.update_or_create(
                        coach=coach, category=category,
                        defaults={"session_rate": rate_val}
                    )
                    saved += 1
                except (ValueError, TypeError):
                    continue

        messages.success(request, f"{saved} نرخ ذخیره شد.{f' {removed} نرخ حذف شد.' if removed else ''}")
        return redirect("payroll:coach-rate-manage")


# ══════════════════════════════════════════════════════════════════════
#  جدول وضعیت پرداخت شهریه بازیکنان — برای مدیر فنی + مدیر مالی
# ══════════════════════════════════════════════════════════════════════

class PlayerPaymentStatusView(FinanceAccessMixin, TemplateView):
    """
    جدول ماهانه وضعیت شهریه همه بازیکنان به تفکیک دسته.
    مدیر فنی: فقط مشاهده
    مدیر مالی: تأیید پرداخت، تغییر وضعیت
    """
    template_name = "payroll/player_payment_status.html"

    def get_context_data(self, **kwargs):
        ctx   = super().get_context_data(**kwargs)
        month = parse_jalali_month_from_request(
            self.request.GET.get("year"),
            self.request.GET.get("month"),
        )

        category_pk = self.request.GET.get("category")
        categories  = TrainingCategory.objects.filter(is_active=True).order_by("name")
        selected_cat = None

        if category_pk:
            try:
                selected_cat = TrainingCategory.objects.get(pk=category_pk)
            except TrainingCategory.DoesNotExist:
                pass

        if selected_cat:
            invoices = PlayerInvoice.objects.filter(
                category=selected_cat,
                jalali_year=month.year,
                jalali_month=month.month,
            ).select_related("player", "confirmed_by").order_by("player__last_name")
        else:
            invoices = PlayerInvoice.objects.filter(
                jalali_year=month.year,
                jalali_month=month.month,
            ).select_related("player", "category", "confirmed_by").order_by("category__name", "player__last_name")

        # آمار کلی
        stats = {
            "paid":            invoices.filter(status="paid").count(),
            "pending":         invoices.filter(status="pending").count(),
            "debtor":          invoices.filter(status="debtor").count(),
            "pending_confirm": invoices.filter(status="pending_confirm").count(),
            "total_collected": invoices.filter(status="paid").aggregate(s=Sum("final_amount"))["s"] or 0,
            "total_pending":   invoices.filter(status__in=["pending","debtor"]).aggregate(s=Sum("final_amount"))["s"] or 0,
        }

        ctx.update({
            "month":        month,
            "prev_month":   month.prev_month,
            "next_month":   month.next_month,
            "categories":   categories,
            "selected_cat": selected_cat,
            "invoices":     invoices,
            "stats":        stats,
            "status_choices": PlayerInvoice.PaymentStatus.choices,
        })
        return ctx