"""
futsal_club/views/coach_payroll_view.py
─────────────────────────────────────────────────────────────────────
خلاصه حقوق مربیان — پرداخت یکجا توسط مدیر مالی
"""
from __future__ import annotations

import json
import logging

from django.contrib import messages
from django.contrib.auth.mixins import LoginRequiredMixin
from django.db import transaction
from django.db.models import Sum, Q
from django.http import JsonResponse
from django.shortcuts import redirect
from django.views import View
from django.views.generic import TemplateView

from ..mixins import RoleRequiredMixin
from ..models import Coach, CoachSalary, Notification
from ..utils.jalali_utils import JalaliMonth
from ..services.payroll_service import PayrollService

logger = logging.getLogger(__name__)


class FinanceMixin(LoginRequiredMixin, RoleRequiredMixin):
    allowed_roles = ["is_finance_manager", "is_technical_director"]


# ──────────────────────────────────────────────────────────────────
#  صفحه خلاصه حقوق مربیان
# ──────────────────────────────────────────────────────────────────
class CoachPayrollSummaryView(FinanceMixin, TemplateView):
    """
    نمایش جمع کل حقوق هر مربی بر اساس رکوردهای CoachSalary
    با وضعیت APPROVED که هنوز پرداخت نشده‌اند (PAID نشده).
    مدیر مالی می‌تواند:
      - تک‌تک یا دسته‌جمعی بزند «پرداخت شد»
      - اعلان رسید برای مربی ارسال شود
    """
    template_name = "payroll/coach_payroll_summary.html"

    def _get_month(self):
        y = self.request.GET.get("year")
        m = self.request.GET.get("month")
        try:
            return JalaliMonth(int(y), int(m))
        except Exception:
            return JalaliMonth.current()

    def get_context_data(self, **kwargs):
        ctx   = super().get_context_data(**kwargs)
        month = self._get_month()
        ctx["month"]      = month
        ctx["prev_month"] = month.prev_month
        ctx["next_month"] = month.next_month

        # رکوردهای approved یا calculated این ماه
        salaries = CoachSalary.objects.filter(
            attendance_sheet__jalali_year=month.year,
            attendance_sheet__jalali_month=month.month,
        ).select_related("coach__user", "category").order_by("coach__last_name")

        # گروه‌بندی بر اساس مربی
        coach_map = {}
        for s in salaries:
            cid = s.coach.pk
            if cid not in coach_map:
                coach_map[cid] = {
                    "coach":      s.coach,
                    "salaries":   [],
                    "total":      0,
                    "approved":   0,
                    "calculated": 0,
                    "paid":       0,
                    "all_paid":   False,
                    "can_pay":    False,
                }
            entry = coach_map[cid]
            entry["salaries"].append(s)
            entry["total"] += int(s.final_amount)
            if s.status == CoachSalary.SalaryStatus.APPROVED:
                entry["approved"] += int(s.final_amount)
                entry["can_pay"]   = True
            elif s.status == CoachSalary.SalaryStatus.CALCULATED:
                entry["calculated"] += int(s.final_amount)
            elif s.status == CoachSalary.SalaryStatus.PAID:
                entry["paid"] += int(s.final_amount)

        for entry in coach_map.values():
            entry["all_paid"] = (entry["approved"] == 0 and entry["calculated"] == 0 and entry["paid"] > 0)

        ctx["coaches"]          = list(coach_map.values())
        ctx["grand_total"]      = sum(e["total"]    for e in coach_map.values())
        ctx["grand_approved"]   = sum(e["approved"] for e in coach_map.values())
        ctx["grand_paid"]       = sum(e["paid"]     for e in coach_map.values())
        ctx["any_payable"]      = any(e["can_pay"]  for e in coach_map.values())
        return ctx


# ──────────────────────────────────────────────────────────────────
#  AJAX: پرداخت حقوق مربی/مربیان
# ──────────────────────────────────────────────────────────────────
class PayCoachSalaryView(LoginRequiredMixin, RoleRequiredMixin, View):
    """
    POST /payroll/coach-payroll/pay/
    body: { coach_ids: [1,2,...], year: 1403, month: 6 }
    وضعیت approved → paid + ارسال اعلان رسید به مربی
    """
    allowed_roles     = ["is_finance_manager"]
    http_method_names = ["post"]

    @transaction.atomic
    def post(self, request):
        try:
            data      = json.loads(request.body)
            coach_ids = [int(x) for x in data.get("coach_ids", [])]
            year      = int(data["year"])
            month_num = int(data["month"])
        except (KeyError, ValueError, json.JSONDecodeError) as e:
            return JsonResponse({"ok": False, "error": str(e)}, status=400)

        if not coach_ids:
            return JsonResponse({"ok": False, "error": "هیچ مربی‌ای انتخاب نشده"}, status=400)

        salaries = CoachSalary.objects.filter(
            coach__pk__in=coach_ids,
            status=CoachSalary.SalaryStatus.APPROVED,
            attendance_sheet__jalali_year=year,
            attendance_sheet__jalali_month=month_num,
        ).select_related("coach__user", "category")

        paid_coaches = {}
        for salary in salaries:
            try:
                PayrollService.mark_salary_paid(salary, paid_by=request.user)
                cid = salary.coach.pk
                if cid not in paid_coaches:
                    paid_coaches[cid] = {"coach": salary.coach, "total": 0, "categories": []}
                paid_coaches[cid]["total"]      += int(salary.final_amount)
                paid_coaches[cid]["categories"].append(salary.category.name)
            except ValueError as e:
                logger.warning("Pay salary failed: %s", e)

        # ارسال اعلان رسید به هر مربی
        for entry in paid_coaches.values():
            coach = entry["coach"]
            if coach.user:
                cat_list = "، ".join(entry["categories"])
                card_hint = ""
                if coach.bank_card_number:
                    card_hint = f"\nشماره کارت: ****-{coach.bank_card_number[-4:]}"

                Notification.objects.create(
                    recipient=coach.user,
                    type=Notification.NotificationType.GENERAL,
                    title="💰 رسید پرداخت حقوق",
                    message=(
                        f"حقوق شما برای ماه {year}/{month_num:02d} "
                        f"در دسته‌های [{cat_list}] "
                        f"به مبلغ {entry['total']:,} ریال پرداخت شد.{card_hint}"
                    ),
                )

        return JsonResponse({
            "ok":          True,
            "paid_count":  len(paid_coaches),
            "total_paid":  sum(e["total"] for e in paid_coaches.values()),
            "coaches":     [
                {"name": f"{e['coach'].first_name} {e['coach'].last_name}", "total": e["total"]}
                for e in paid_coaches.values()
            ],
        })
