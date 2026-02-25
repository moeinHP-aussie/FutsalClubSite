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
from ..models import Coach, CoachSalary, Notification, TrainingCategory
from ..services.jalali_utils import JalaliMonth, parse_jalali_month_from_request
from ..services.payroll_service import PayrollService

logger = logging.getLogger(__name__)


class FinanceMixin(LoginRequiredMixin, RoleRequiredMixin):
    allowed_roles = ["is_finance_manager", "is_technical_director"]


# ──────────────────────────────────────────────────────────────────
#  صفحه خلاصه حقوق مربیان
# ──────────────────────────────────────────────────────────────────
class CoachPayrollSummaryView(FinanceMixin, TemplateView):
    """داشبورد حقوق مربیان — نمای دسته‌بندی با آمار"""
    template_name  = "payroll/coach_payroll_summary.html"
    allowed_roles  = ["finance_manager", "technical_director", "superuser"]

    def get_context_data(self, **kwargs):
        from futsal_club.services.jalali_utils import parse_jalali_month_from_request
        ctx   = super().get_context_data(**kwargs)
        month = parse_jalali_month_from_request(
            self.request.GET.get("year"),
            self.request.GET.get("month"),
        )
        categories = TrainingCategory.objects.filter(is_active=True).order_by("name")
        cat_data = []
        for cat in categories:
            sals = CoachSalary.objects.filter(
                category=cat,
                attendance_sheet__jalali_year=month.year,
                attendance_sheet__jalali_month=month.month,
            )
            cat_data.append({
                "pk":              cat.pk,
                "name":            cat.name,
                "coach_count":     sals.count(),
                "confirmed_count": sals.filter(status=CoachSalary.SalaryStatus.CONFIRMED).count(),
                "paid_count":      sals.filter(status=CoachSalary.SalaryStatus.PAID).count(),
                "pending_count":   sals.filter(status__in=["calculated","approved"]).count(),
            })
        ctx.update({
            "month":      month,
            "prev_month": month.prev_month,
            "next_month": month.next_month,
            "categories": cat_data,
        })
        return ctx