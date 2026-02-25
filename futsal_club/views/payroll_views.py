"""
views/payroll_views.py
─────────────────────────────────────────────────────────────────────
ویوهای مدیریت حقوق و فاکتور — Class-Based Views
"""

from __future__ import annotations

import logging
from decimal import Decimal, InvalidOperation

from django.contrib import messages
from django.contrib.auth.mixins import LoginRequiredMixin
from django.http import JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.utils.translation import gettext_lazy as _
from django.views import View
from django.views.generic import ListView, TemplateView

from ..mixins import RoleRequiredMixin
from ..models import (
    Coach,
    CoachSalary,
    PlayerInvoice,
    TrainingCategory,
)
from ..services.payroll_service import PayrollService
from ..services.jalali_utils import JalaliMonth, parse_jalali_month_from_request

logger = logging.getLogger(__name__)


# ────────────────────────────────────────────────────────────────────
#  Permission Mixins
# ────────────────────────────────────────────────────────────────────

class FinanceAccessMixin(LoginRequiredMixin, RoleRequiredMixin):
    """مدیر مالی یا مدیر فنی."""
    allowed_roles = ["is_finance_manager", "is_technical_director"]


class FinanceOnlyMixin(LoginRequiredMixin, RoleRequiredMixin):
    """فقط مدیر مالی."""
    allowed_roles = ["is_finance_manager"]


# ────────────────────────────────────────────────────────────────────
#  1. Coach Salary Preview & Commit
# ────────────────────────────────────────────────────────────────────

class CoachSalaryCalculateView(FinanceAccessMixin, TemplateView):
    """
    محاسبه پیش‌نمایش حقوق یک مربی در یک دسته.

    GET  ?year=1403&month=5     → نمایش پیش‌نمایش
    POST                        → ذخیره رکورد حقوق
    """
    template_name = "payroll/salary_preview.html"

    def _get_params(self):
        coach    = get_object_or_404(Coach, pk=self.kwargs["coach_pk"])
        category = get_object_or_404(TrainingCategory, pk=self.kwargs["category_pk"])
        month    = parse_jalali_month_from_request(
            self.request.GET.get("year") or self.request.POST.get("year"),
            self.request.GET.get("month") or self.request.POST.get("month"),
        )
        return coach, category, month

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        coach, category, month = self._get_params()

        try:
            breakdown = PayrollService.calculate_coach_salary(
                coach=coach,
                category=category,
                jalali_month=month,
            )
            ctx["breakdown"]  = breakdown
            ctx["error"]      = None
        except ValueError as e:
            ctx["breakdown"]  = None
            ctx["error"]      = str(e)

        ctx.update(
            {
                "coach":    coach,
                "category": category,
                "month":    month,
                "prev_month": month.prev_month,
                "next_month": month.next_month,
            }
        )
        return ctx

    def post(self, request, coach_pk: int, category_pk: int):
        coach    = get_object_or_404(Coach, pk=coach_pk)
        category = get_object_or_404(TrainingCategory, pk=category_pk)
        month    = parse_jalali_month_from_request(
            request.POST.get("year"),
            request.POST.get("month"),
        )

        # ── تعدیل دستی ──────────────────────────────────────────
        try:
            adjustment = Decimal(request.POST.get("manual_adjustment", "0"))
        except InvalidOperation:
            messages.error(request, "مقدار تعدیل دستی معتبر نیست.")
            return redirect(
                "payroll:salary-calculate",
                coach_pk=coach_pk, category_pk=category_pk,
            )

        reason = request.POST.get("adjustment_reason", "")

        try:
            breakdown = PayrollService.calculate_coach_salary(
                coach=coach,
                category=category,
                jalali_month=month,
                manual_adjustment=adjustment,
                adjustment_reason=reason,
            )
            salary = PayrollService.commit_coach_salary(breakdown, request.user)
            messages.success(
                request,
                f"حقوق {coach} برای {month} به مبلغ "
                f"{salary.final_amount:,.0f} ریال ذخیره شد.",
            )
        except ValueError as e:
            messages.error(request, str(e))
            return redirect(
                "payroll:salary-calculate",
                coach_pk=coach_pk, category_pk=category_pk,
            )

        return redirect("payroll:salary-list", category_pk=category_pk)


# ────────────────────────────────────────────────────────────────────
#  2. Bulk Salary Calculation (All Coaches in a Category)
# ────────────────────────────────────────────────────────────────────

class BulkSalaryCalculateView(FinanceAccessMixin, TemplateView):
    """
    محاسبه یکجا حقوق تمام مربیان یک دسته در یک ماه.
    GET  → نمایش پیش‌نمایش
    POST → ذخیره تمام رکوردها
    """
    template_name = "payroll/bulk_salary.html"

    def _get_params(self):
        category = get_object_or_404(TrainingCategory, pk=self.kwargs["category_pk"])
        month    = parse_jalali_month_from_request(
            self.request.GET.get("year") or self.request.POST.get("year"),
            self.request.GET.get("month") or self.request.POST.get("month"),
        )
        return category, month

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        category, month = self._get_params()

        breakdowns = PayrollService.calculate_all_coaches_for_month(
            category=category,
            jalali_month=month,
            processed_by=self.request.user,
        )

        ctx.update(
            {
                "category":   category,
                "month":      month,
                "breakdowns": breakdowns,
                "total":      sum(b.final_amount for b in breakdowns),
                "prev_month": month.prev_month,
                "next_month": month.next_month,
            }
        )
        return ctx

    def post(self, request, category_pk: int):
        category, month = self._get_params()
        breakdowns = PayrollService.calculate_all_coaches_for_month(
            category=category, jalali_month=month, processed_by=request.user
        )

        saved = 0
        for bd in breakdowns:
            # بررسی تعدیل دستی برای هر مربی
            adj_key = f"adjustment_{bd.coach.pk}"
            reason_key = f"reason_{bd.coach.pk}"
            try:
                adj = Decimal(request.POST.get(adj_key, "0"))
            except InvalidOperation:
                adj = Decimal("0")
            reason = request.POST.get(reason_key, "")

            # محاسبه مجدد با تعدیل
            bd_adj = PayrollService.calculate_coach_salary(
                coach=bd.coach,
                category=category,
                jalali_month=month,
                manual_adjustment=adj,
                adjustment_reason=reason,
            )
            PayrollService.commit_coach_salary(bd_adj, request.user)
            saved += 1

        messages.success(request, f"حقوق {saved} مربی برای {month} ذخیره شد.")
        return redirect("payroll:salary-list", category_pk=category_pk)


# ────────────────────────────────────────────────────────────────────
#  3. Salary List View
# ────────────────────────────────────────────────────────────────────

class SalaryListView(FinanceAccessMixin, ListView):
    """لیست حقوق‌های یک دسته با فیلتر ماه."""
    template_name       = "payroll/salary_list.html"
    context_object_name = "salaries"
    paginate_by         = 20

    def get_queryset(self):
        self.category = get_object_or_404(
            TrainingCategory, pk=self.kwargs["category_pk"]
        )
        self.month = parse_jalali_month_from_request(
            self.request.GET.get("year"),
            self.request.GET.get("month"),
        )
        return (
            CoachSalary.objects
            .filter(
                category=self.category,
                attendance_sheet__jalali_year=self.month.year,
                attendance_sheet__jalali_month=self.month.month,
            )
            .select_related("coach", "attendance_sheet")
            .order_by("coach__last_name")
        )

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        qs  = self.get_queryset()
        ctx.update(
            {
                "category":     self.category,
                "month":        self.month,
                "prev_month":   self.month.prev_month,
                "next_month":   self.month.next_month,
                "total_amount": sum(s.final_amount for s in qs),
                "paid_count":   qs.filter(status="paid").count(),
            }
        )
        return ctx


# ────────────────────────────────────────────────────────────────────
#  4. Salary Approve / Pay Actions
# ────────────────────────────────────────────────────────────────────

class ApproveSalaryView(FinanceOnlyMixin, View):
    """تأیید رکورد حقوق توسط مدیر مالی."""
    http_method_names = ["post"]

    def post(self, request, salary_pk: int):
        salary = get_object_or_404(CoachSalary, pk=salary_pk)
        try:
            PayrollService.approve_salary(salary, approved_by=request.user)
            messages.success(request, f"حقوق {salary.coach} تأیید شد.")
        except ValueError as e:
            messages.error(request, str(e))
        return redirect("payroll:salary-list", category_pk=salary.category_id)


class MarkSalaryPaidView(FinanceOnlyMixin, View):
    """پرداخت حقوق."""
    http_method_names = ["post"]

    def post(self, request, salary_pk: int):
        salary = get_object_or_404(CoachSalary, pk=salary_pk)
        try:
            PayrollService.mark_salary_paid(salary, paid_by=request.user)
            messages.success(request, f"حقوق {salary.coach} پرداخت شد.")
        except ValueError as e:
            messages.error(request, str(e))
        return redirect("payroll:salary-list", category_pk=salary.category_id)


# ────────────────────────────────────────────────────────────────────
#  5. Monthly Invoice Generation
# ────────────────────────────────────────────────────────────────────

class GenerateMonthlyInvoicesView(FinanceOnlyMixin, View):
    """
    صدور فاکتور ماهانه برای یک دسته.
    POST  /payroll/invoices/generate/<category_pk>/
    """
    http_method_names = ["post"]

    def post(self, request, category_pk: int):
        category = get_object_or_404(TrainingCategory, pk=category_pk)
        month    = parse_jalali_month_from_request(
            request.POST.get("year"),
            request.POST.get("month"),
        )

        batch = PayrollService.generate_monthly_invoices(
            category=category,
            jalali_month=month,
            created_by=request.user,
        )

        if batch.error_count:
            messages.warning(
                request,
                f"{batch.created_count} فاکتور ایجاد شد، "
                f"{batch.skipped_count} تکراری رد شد، "
                f"{batch.error_count} خطا داشت.",
            )
        else:
            messages.success(
                request,
                f"{batch.created_count} فاکتور برای {month} ایجاد شد. "
                f"{batch.skipped_count} مورد قبلاً وجود داشت.",
            )

        return redirect("payroll:invoice-list", category_pk=category_pk)


class GenerateAllCategoryInvoicesView(FinanceOnlyMixin, View):
    """
    صدور فاکتور برای تمام دسته‌ها — ماه انتخاب‌شده از داشبورد.
    POST  /payroll/invoices/generate-all/
    پارامترهای POST: year, month  (اگر نباشند، ماه جاری)
    """
    http_method_names = ["post"]

    def post(self, request):
        # ✅ Bug fix: ماه را از POST بخوان نه همیشه ماه جاری
        month = parse_jalali_month_from_request(
            request.POST.get("year"),
            request.POST.get("month"),
        )
        results = PayrollService.generate_invoices_all_categories(
            jalali_month=month, created_by=request.user
        )
        total_created = sum(b.created_count for b in results.values())
        messages.success(
            request,
            f"{total_created} فاکتور برای {month} در تمام دسته‌ها صادر شد.",
        )
        from django.urls import reverse
        url = reverse("payroll:finance-dashboard") + f"?year={month.year}&month={month.month}"
        return redirect(url)


# ────────────────────────────────────────────────────────────────────
#  6. Invoice List & Management
# ────────────────────────────────────────────────────────────────────

class InvoiceListView(FinanceAccessMixin, ListView):
    """لیست فاکتورهای یک دسته با فیلتر ماه و وضعیت."""
    template_name       = "payroll/invoice_list.html"
    context_object_name = "invoices"
    paginate_by         = 25

    def get_queryset(self):
        self.category = get_object_or_404(
            TrainingCategory, pk=self.kwargs["category_pk"]
        )
        self.month = parse_jalali_month_from_request(
            self.request.GET.get("year"),
            self.request.GET.get("month"),
        )
        qs = PlayerInvoice.objects.filter(
            category=self.category,
            jalali_year=self.month.year,
            jalali_month=self.month.month,
        ).select_related("player", "confirmed_by")

        status_filter = self.request.GET.get("status")
        if status_filter:
            qs = qs.filter(status=status_filter)

        return qs.order_by("player__last_name")

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        qs  = self.get_queryset()
        ctx.update(
            {
                "category":     self.category,
                "month":        self.month,
                "prev_month":   self.month.prev_month,
                "next_month":   self.month.next_month,
                "status_counts": {
                    "pending":         qs.filter(status="pending").count(),
                    "paid":            qs.filter(status="paid").count(),
                    "debtor":          qs.filter(status="debtor").count(),
                    "pending_confirm": qs.filter(status="pending_confirm").count(),
                },
                "total_due":    sum(i.final_amount for i in qs.filter(status__in=["pending", "debtor"])),
                "total_paid":   sum(i.final_amount for i in qs.filter(status="paid")),
                "status_choices": PlayerInvoice.PaymentStatus.choices,
                "pending_confirm_count": qs.filter(status="pending_confirm").count(),
            }
        )
        return ctx


class ConfirmInvoicePaymentView(FinanceOnlyMixin, View):
    """تأیید دستی پرداخت فاکتور توسط مدیر مالی."""
    http_method_names = ["post"]

    def post(self, request, invoice_pk: int):
        invoice = get_object_or_404(PlayerInvoice, pk=invoice_pk)
        try:
            PayrollService.confirm_invoice_payment(invoice, confirmed_by=request.user)
            messages.success(request, f"پرداخت فاکتور {invoice} تأیید شد.")
        except ValueError as e:
            messages.error(request, str(e))
        return redirect(
            "payroll:invoice-list",
            category_pk=invoice.category_id,
        )


class UploadReceiptView(LoginRequiredMixin, View):
    """
    آپلود رسید پرداخت توسط بازیکن.
    POST  /payroll/invoice/<invoice_pk>/receipt/
    """
    http_method_names = ["post"]

    def post(self, request, invoice_pk: int):
        invoice = get_object_or_404(PlayerInvoice, pk=invoice_pk)

        # بررسی تعلق فاکتور به بازیکن لاگین‌شده
        if (
            hasattr(request.user, "player_profile")
            and invoice.player != request.user.player_profile
            and not request.user.is_finance_manager
        ):
            messages.error(request, "دسترسی غیرمجاز.")
            return redirect("accounts:dashboard")

        receipt = request.FILES.get("receipt_image")
        if not receipt:
            messages.error(request, "فایل رسید انتخاب نشده است.")
            return redirect("payroll:invoice-list", category_pk=invoice.category_id)

        try:
            PayrollService.upload_receipt(invoice, receipt)
            messages.success(request, "رسید آپلود شد و در انتظار تأیید است.")
        except ValueError as e:
            messages.error(request, str(e))

        return redirect("payroll:invoice-list", category_pk=invoice.category_id)


# ────────────────────────────────────────────────────────────────────
#  7. Finance Dashboard
# ────────────────────────────────────────────────────────────────────

class FinanceDashboardView(FinanceAccessMixin, TemplateView):
    """
    داشبورد مالی — خلاصه ماه جاری:
    - کل فاکتورها (پرداخت شده / بدهکار / در انتظار)
    - کل حقوق‌های محاسبه‌شده
    - اعلان‌های بیمه در حال انقضا
    """
    template_name = "payroll/finance_dashboard.html"

    def get_context_data(self, **kwargs):
        ctx   = super().get_context_data(**kwargs)
        month = parse_jalali_month_from_request(
            self.request.GET.get("year"),
            self.request.GET.get("month"),
        )

        invoices = PlayerInvoice.objects.filter(
            jalali_year=month.year,
            jalali_month=month.month,
        )
        salaries = CoachSalary.objects.filter(
            attendance_sheet__jalali_year=month.year,
            attendance_sheet__jalali_month=month.month,
        )

        ctx.update(
            {
                "month":        month,
                "prev_month":   month.prev_month,
                "invoice_summary": {
                    "total":    invoices.count(),
                    "paid":     invoices.filter(status="paid").count(),
                    "debtor":   invoices.filter(status="debtor").count(),
                    "pending":  invoices.filter(status="pending").count(),
                    "confirm":  invoices.filter(status="pending_confirm").count(),
                    "amount_paid":   sum(
                        i.final_amount for i in invoices.filter(status="paid")
                    ),
                    "amount_pending": sum(
                        i.final_amount for i in invoices.exclude(status="paid")
                    ),
                },
                "salary_summary": {
                    "total":    salaries.count(),
                    "paid":     salaries.filter(status="paid").count(),
                    "approved": salaries.filter(status="approved").count(),
                    "pending":  salaries.filter(status="calculated").count(),
                    "total_amount": sum(s.final_amount for s in salaries),
                },
                "categories": TrainingCategory.objects.filter(is_active=True),
            }
        )
        return ctx