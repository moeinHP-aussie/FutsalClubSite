"""
views/attendance_views.py
─────────────────────────────────────────────────────────────────────
ویوهای حضور و غیاب — Class-Based Views
"""

from __future__ import annotations

import json
import logging

from django.contrib import messages
from django.contrib.auth.mixins import LoginRequiredMixin
from django.http import JsonResponse
from django.shortcuts import get_object_or_404, redirect
from django.urls import reverse_lazy
from django.utils.translation import gettext_lazy as _
from django.views import View
from django.views.generic import DetailView, ListView, TemplateView

from ..mixins import RoleRequiredMixin
from ..models import (
    AttendanceSheet,
    Coach,
    Player,
    SessionDate,
    TrainingCategory,
)
from ..services.attendance_service import AttendanceService
from ..services.jalali_utils import JalaliMonth, parse_jalali_month_from_request

logger = logging.getLogger(__name__)


# ────────────────────────────────────────────────────────────────────
#  Permission Mixin
# ────────────────────────────────────────────────────────────────────

class AttendancePermissionMixin(LoginRequiredMixin, RoleRequiredMixin):
    """دسترسی به حضور و غیاب: مربی یا مدیر فنی."""
    allowed_roles = ["is_coach", "is_technical_director"]


# ────────────────────────────────────────────────────────────────────
#  1. Attendance Matrix View
# ────────────────────────────────────────────────────────────────────

class AttendanceMatrixView(AttendancePermissionMixin, TemplateView):
    """
    ماتریس حضور و غیاب ماهانه برای یک دسته آموزشی.
    GET  ?year=1403&month=5   → نمایش ماتریس

    سطرها: بازیکنان + مربیان دسته
    ستون‌ها: تاریخ هر جلسه
    """
    template_name = "attendance/matrix.html"

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)

        category = get_object_or_404(
            TrainingCategory, pk=self.kwargs["category_pk"], is_active=True
        )
        jalali_month = parse_jalali_month_from_request(
            self.request.GET.get("year"),
            self.request.GET.get("month"),
        )

        matrix = AttendanceService.build_attendance_matrix(category, jalali_month)

        ctx.update(
            {
                "category":       category,
                "jalali_month":   jalali_month,
                "matrix":         matrix,
                "prev_month":     jalali_month.prev_month,
                "next_month":     jalali_month.next_month,
                "status_choices": {
                    "present": "حاضر",
                    "absent":  "غایب",
                    "excused": "غیبت موجه",
                },
                # ارسال session_ids برای ساخت هدر جدول
                "session_dates":  matrix.session_dates,
                "can_edit":       not matrix.sheet.is_finalized,
            }
        )
        return ctx


# ────────────────────────────────────────────────────────────────────
#  2. Session Quick-Record View (AJAX)
# ────────────────────────────────────────────────────────────────────

class RecordSessionAttendanceView(AttendancePermissionMixin, View):
    """
    ثبت حضور یک جلسه کامل از طریق AJAX.
    POST  /attendance/session/<session_pk>/record/

    body (JSON):
    {
        "players": [
            {"player_id": 42, "status": "present", "note": ""},
            {"player_id": 17, "status": "absent",  "note": "بیماری"}
        ],
        "coaches": [
            {"coach_id": 3, "status": "present", "note": ""}
        ]
    }
    """
    http_method_names = ["post"]

    def post(self, request, session_pk: int):
        session = get_object_or_404(SessionDate, pk=session_pk)

        # ── بررسی دسترسی مربی به این دسته ─────────────────────────
        if request.user.is_coach and not request.user.is_technical_director:
            allowed_cats = CoachCategoryRate.objects.filter(
                coach__user=request.user, is_active=True
            ).values_list("category_id", flat=True)
            if session.sheet.category_id not in allowed_cats:
                return JsonResponse(
                    {"error": "دسترسی به این رده آموزشی مجاز نیست."}, status=403
                )

        try:
            payload = json.loads(request.body)
        except json.JSONDecodeError:
            return JsonResponse({"error": "داده ارسالی معتبر نیست."}, status=400)

        try:
            result = AttendanceService.record_full_session(
                session=session,
                player_data=payload.get("players", []),
                coach_data=payload.get("coaches", []),
                recorded_by=request.user,
            )
        except PermissionError as e:
            return JsonResponse({"error": str(e)}, status=403)
        except Exception as e:
            logger.exception("خطا در ثبت حضور جلسه %s", session_pk)
            return JsonResponse({"error": str(e)}, status=500)

        return JsonResponse(
            {
                "success":  True,
                "players":  len(result["players"]),
                "coaches":  len(result["coaches"]),
                "message":  "حضور و غیاب با موفقیت ثبت شد.",
            }
        )


# ────────────────────────────────────────────────────────────────────
#  3. Single Session Detail View (Form-based)
# ────────────────────────────────────────────────────────────────────

class SessionAttendanceDetailView(AttendancePermissionMixin, TemplateView):
    """
    نمایش و ثبت حضور یک جلسه به صورت فرم.
    ردیف‌های بازیکنان و مربیان دسته با checkbox‌های وضعیت نمایش داده می‌شوند.
    """
    template_name = "attendance/session_detail.html"

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        session = get_object_or_404(SessionDate, pk=self.kwargs["session_pk"])
        sheet   = session.sheet
        category = sheet.category

        # بازیکنان فعال دسته
        players = list(
            category.players.filter(status="approved", is_archived=False)
            .order_by("last_name")
        )

        # مربیان فعال دسته
        coaches = list(
            Coach.objects.filter(
                coachcategoryrate__category=category,
                coachcategoryrate__is_active=True,
                is_active=True,
            ).distinct()
        )

        # رکوردهای موجود این جلسه
        existing_player_att = {
            r.player_id: r
            for r in session.player_records.all()
        }
        existing_coach_att = {
            r.coach_id: r
            for r in session.coach_records.all()
        }

        # ساخت context برای فرم
        player_rows = []
        for p in players:
            existing = existing_player_att.get(p.pk)
            player_rows.append(
                {
                    "player":  p,
                    "status":  existing.status if existing else "absent",
                    "note":    existing.note   if existing else "",
                }
            )

        coach_rows = []
        for c in coaches:
            existing = existing_coach_att.get(c.pk)
            coach_rows.append(
                {
                    "coach":  c,
                    "status": existing.status if existing else "absent",
                    "note":   existing.note   if existing else "",
                }
            )

        ctx.update(
            {
                "session":     session,
                "sheet":       sheet,
                "category":    category,
                "player_rows": player_rows,
                "coach_rows":  coach_rows,
                "can_edit":    not sheet.is_finalized,
                "status_choices": [
                    ("present", "حاضر"),
                    ("absent",  "غایب"),
                    ("excused", "غیبت موجه"),
                ],
            }
        )
        return ctx

    def post(self, request, session_pk: int):
        session = get_object_or_404(SessionDate, pk=session_pk)
        sheet   = session.sheet

        if sheet.is_finalized:
            messages.error(request, "این لیست نهایی شده و قابل ویرایش نیست.")
            return redirect("attendance:session-detail", session_pk=session_pk)

        category = sheet.category

        # ── پردازش داده فرم ─────────────────────────────────────
        player_data = []
        for player in category.players.filter(status="approved", is_archived=False):
            key    = f"player_{player.pk}_status"
            status = request.POST.get(key, "absent")
            note   = request.POST.get(f"player_{player.pk}_note", "")
            player_data.append(
                {"player_id": player.pk, "status": status, "note": note}
            )

        coach_data = []
        for coach in Coach.objects.filter(
            coachcategoryrate__category=category,
            coachcategoryrate__is_active=True,
            is_active=True,
        ).distinct():
            key    = f"coach_{coach.pk}_status"
            status = request.POST.get(key, "absent")
            note   = request.POST.get(f"coach_{coach.pk}_note", "")
            coach_data.append(
                {"coach_id": coach.pk, "status": status, "note": note}
            )

        try:
            AttendanceService.record_full_session(
                session=session,
                player_data=player_data,
                coach_data=coach_data,
                recorded_by=request.user,
            )
            messages.success(request, "حضور و غیاب با موفقیت ثبت شد.")
        except Exception as e:
            messages.error(request, f"خطا در ثبت: {e}")

        return redirect(
            "attendance:matrix",
            category_pk=category.pk,
        )


# ────────────────────────────────────────────────────────────────────
#  4. Finalize Sheet View
# ────────────────────────────────────────────────────────────────────

class FinalizeAttendanceSheetView(LoginRequiredMixin, RoleRequiredMixin, View):
    """
    نهایی کردن لیست حضور و غیاب — فقط مدیر فنی.
    POST  /attendance/sheet/<sheet_pk>/finalize/
    """
    allowed_roles    = ["is_technical_director"]
    http_method_names = ["post"]

    def post(self, request, sheet_pk: int):
        sheet = get_object_or_404(AttendanceSheet, pk=sheet_pk)

        try:
            AttendanceService.finalize_sheet(sheet, finalized_by=request.user)
            messages.success(request, f"لیست {sheet} با موفقیت نهایی شد.")
        except (ValueError, PermissionError) as e:
            messages.error(request, str(e))

        return redirect(
            "attendance:matrix",
            category_pk=sheet.category_id,
        )


# ────────────────────────────────────────────────────────────────────
#  5. Sheet List View
# ────────────────────────────────────────────────────────────────────

class AttendanceSheetListView(AttendancePermissionMixin, ListView):
    """لیست تمام لیست‌های حضور و غیاب برای یک دسته."""
    template_name = "attendance/sheet_list.html"
    context_object_name = "sheets"
    paginate_by = 12

    def get_queryset(self):
        self.category = get_object_or_404(
            TrainingCategory, pk=self.kwargs["category_pk"]
        )
        return (
            AttendanceSheet.objects
            .filter(category=self.category)
            .order_by("-jalali_year", "-jalali_month")
        )

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx["category"] = self.category
        return ctx


# ────────────────────────────────────────────────────────────────────
#  6. Player Attendance History View
# ────────────────────────────────────────────────────────────────────

class PlayerAttendanceHistoryView(AttendancePermissionMixin, TemplateView):
    """تاریخچه حضور یک بازیکن در چند ماه گذشته."""
    template_name = "attendance/player_history.html"

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        player = get_object_or_404(Player, pk=self.kwargs["player_pk"])

        # ماه‌های اخیر (۶ ماه گذشته)
        current = JalaliMonth.current()
        months  = [current]
        for _ in range(5):
            current = current.prev_month
            months.append(current)

        monthly_stats = {}
        for month in months:
            monthly_stats[str(month)] = AttendanceService.get_player_monthly_stats(
                player, month
            )

        ctx.update(
            {
                "player":        player,
                "monthly_stats": monthly_stats,
                "months":        months,
            }
        )
        return ctx