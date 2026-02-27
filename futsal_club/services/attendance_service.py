"""
services/attendance_service.py
─────────────────────────────────────────────────────────────────────
لایه سرویس حضور و غیاب
Handles all attendance logic: sheet generation, recording,
and querying — fully separated from HTTP/View concerns.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Tuple

import jdatetime
from django.db import transaction
from django.utils import timezone

from ..models import (
    AttendanceSheet,
    Coach,
    CoachAttendance,
    CoachCategoryRate,
    Player,
    PlayerAttendance,
    SessionDate,
    TrainingCategory,
    TrainingSchedule,
)
from ..utils.jalali_utils import JalaliMonth, jalali_date_display

logger = logging.getLogger(__name__)


# ────────────────────────────────────────────────────────────────────
#  Data Transfer Objects
# ────────────────────────────────────────────────────────────────────

@dataclass
class AttendanceRecord:
    """وضعیت حضور یک نفر (بازیکن یا مربی) در یک جلسه."""
    session_id: int
    session_date: str          # نمایش شمسی
    entity_id: int             # شناسه بازیکن یا مربی
    entity_name: str
    status: str                # present / absent / excused
    note: str = ""


@dataclass
class AttendanceMatrixRow:
    """یک سطر از ماتریس حضور و غیاب (مربوط به یک بازیکن/مربی)."""
    entity_id: int
    entity_name: str
    entity_type: str           # 'player' | 'coach'
    # کلید: session_id  →  مقدار: status string
    sessions: Dict[int, str] = field(default_factory=dict)

    @property
    def present_count(self) -> int:
        return sum(1 for s in self.sessions.values() if s == "present")

    @property
    def absent_count(self) -> int:
        return sum(1 for s in self.sessions.values() if s == "absent")

    @property
    def excused_count(self) -> int:
        return sum(1 for s in self.sessions.values() if s == "excused")

    @property
    def attendance_pct(self) -> float:
        total = len(self.sessions)
        return round(self.present_count / total * 100, 1) if total else 0.0


@dataclass
class AttendanceMatrixResult:
    """خروجی کامل ماتریس حضور و غیاب برای یک دسته در یک ماه."""
    sheet: Optional[AttendanceSheet]
    category: TrainingCategory
    jalali_month: JalaliMonth
    session_dates: List[SessionDate]
    player_rows: List[AttendanceMatrixRow]
    coach_rows: List[AttendanceMatrixRow]


# ────────────────────────────────────────────────────────────────────
#  Core Service
# ────────────────────────────────────────────────────────────────────

class AttendanceService:
    """
    سرویس اصلی حضور و غیاب.
    تمام منطق کسب‌وکار در اینجاست — بدون وابستگی به Request/Response.
    """

    # ── 1. Sheet Generation ─────────────────────────────────────────

    @classmethod
    @transaction.atomic
    def get_or_create_sheet(
        cls,
        category: TrainingCategory,
        jalali_month: JalaliMonth,
    ) -> Tuple[AttendanceSheet, bool]:
        """
        لیست حضور و غیاب ماهانه را دریافت یا ایجاد می‌کند.

        قوانین:
        - ماه جاری: ساخته می‌شود و SessionDate‌ها با زمان‌بندی sync می‌شوند.
        - ماه‌های گذشته: فقط دریافت می‌شود (اگر وجود داشته باشد) — تغییری نمی‌کند.
        - ماه‌های آینده: شیت ساخته نمی‌شود؛ None برمی‌گرداند.

        Returns: (sheet | None, created: bool)
        """
        current = JalaliMonth.current()

        # ماه آینده → شیت ساخته نمی‌شود
        if (jalali_month.year, jalali_month.month) > (current.year, current.month):
            existing = AttendanceSheet.objects.filter(
                category=category,
                jalali_year=jalali_month.year,
                jalali_month=jalali_month.month,
            ).first()
            return existing, False  # None if not exists

        sheet, created = AttendanceSheet.objects.get_or_create(
            category=category,
            jalali_year=jalali_month.year,
            jalali_month=jalali_month.month,
        )

        if created:
            cls._populate_session_dates(sheet, category, jalali_month)
            logger.info(
                "لیست حضور و غیاب جدید ایجاد شد: %s — %s",
                category, jalali_month
            )
        elif (jalali_month.year, jalali_month.month) == (current.year, current.month):
            # ماه جاری: جلسات جدید را اضافه می‌کند (بدون حذف قدیمی‌ها)
            cls._sync_session_dates(sheet, category, jalali_month)

        return sheet, created

    @staticmethod
    def _populate_session_dates(
        sheet: AttendanceSheet,
        category: TrainingCategory,
        jalali_month: JalaliMonth,
    ) -> List[SessionDate]:
        """
        جلسات ماه را بر اساس زمان‌بندی دسته آموزشی محاسبه و ذخیره می‌کند.
        اگر یک دسته دو زمان‌بندی (مثلاً شنبه + سه‌شنبه) داشته باشد،
        هر دو در نظر گرفته می‌شوند.
        """
        schedules = category.schedules.all()
        if not schedules.exists():
            logger.warning("دسته %s هیچ زمان‌بندی تمرینی ندارد.", category)
            return []

        # جمع‌آوری روزهای هفته فعال
        weekdays = [s.weekday for s in schedules]

        # تمام روزهای ماه که با این روزها تطابق دارند
        matching_days = jalali_month.days_for_weekdays(weekdays)

        session_objects = []
        for idx, jdate in enumerate(matching_days, start=1):
            greg_date = jdate.togregorian()
            sd, _ = SessionDate.objects.get_or_create(
                sheet=sheet,
                date=greg_date,          # django-jalali در DB میلادی ذخیره می‌کند
                defaults={"session_number": idx},
            )
            session_objects.append(sd)

        logger.info(
            "%d جلسه برای %s — %s ایجاد شد.",
            len(session_objects), category, jalali_month
        )
        return session_objects

    @classmethod
    def _sync_session_dates(
        cls,
        sheet: AttendanceSheet,
        category: TrainingCategory,
        jalali_month: JalaliMonth,
    ) -> None:
        """
        برای ماه جاری: جلسات جدید را اضافه می‌کند اما جلسات موجود را حذف نمی‌کند.
        وقتی زمان‌بندی تغییر می‌کند، جلسات تازه اضافه می‌شوند.
        جلسات قدیمی که حضور و غیاب ثبت شده‌اند دست نمی‌خورند.
        """
        schedules = category.schedules.all()
        if not schedules.exists():
            return

        weekdays = [s.weekday for s in schedules]
        matching_days = jalali_month.days_for_weekdays(weekdays)

        existing_dates = set(
            sheet.session_dates.values_list("date", flat=True)
        )

        added = 0
        # شماره‌گذاری از بعد از آخرین جلسه موجود
        from django.db.models import Max as _Max
        last_num = sheet.session_dates.aggregate(m=_Max('session_number'))['m'] or 0

        for idx, jdate in enumerate(matching_days, start=1):
            greg_date = jdate.togregorian()
            if greg_date not in existing_dates:
                SessionDate.objects.get_or_create(
                    sheet=sheet,
                    date=greg_date,
                    defaults={"session_number": last_num + idx},
                )
                added += 1

        if added:
            logger.info(
                "%d جلسه جدید به ماتریس %s — %s اضافه شد.",
                added, category, jalali_month
            )

    # ── 2. Attendance Recording ─────────────────────────────────────

    @classmethod
    @transaction.atomic
    def record_player_attendance(
        cls,
        session: SessionDate,
        attendance_data: List[Dict[str, Any]],
        recorded_by=None,
    ) -> List[PlayerAttendance]:
        """
        ثبت یا به‌روزرسانی حضور چند بازیکن در یک جلسه.

        attendance_data format:
        [
            {"player_id": 42, "status": "present", "note": ""},
            {"player_id": 17, "status": "absent",  "note": "بیماری"},
        ]
        """
        if session.sheet.is_finalized:
            raise PermissionError("این لیست نهایی شده است و قابل ویرایش نیست.")

        results = []
        for item in attendance_data:
            record, _ = PlayerAttendance.objects.update_or_create(
                session=session,
                player_id=item["player_id"],
                defaults={
                    "status": item.get("status", PlayerAttendance.AttendanceStatus.ABSENT),
                    "note":   item.get("note", ""),
                },
            )
            results.append(record)

        logger.info(
            "حضور %d بازیکن در جلسه %s ثبت شد توسط %s.",
            len(results), session, recorded_by
        )
        return results

    @classmethod
    @transaction.atomic
    def record_coach_attendance(
        cls,
        session: SessionDate,
        attendance_data: List[Dict[str, Any]],
        recorded_by=None,
    ) -> List[CoachAttendance]:
        """
        ثبت یا به‌روزرسانی حضور چند مربی در یک جلسه.

        attendance_data format:
        [
            {"coach_id": 3, "status": "present", "note": ""},
        ]
        """
        if session.sheet.is_finalized:
            raise PermissionError("این لیست نهایی شده است و قابل ویرایش نیست.")

        results = []
        for item in attendance_data:
            record, _ = CoachAttendance.objects.update_or_create(
                session=session,
                coach_id=item["coach_id"],
                defaults={
                    "status": item.get("status", CoachAttendance.AttendanceStatus.ABSENT),
                    "note":   item.get("note", ""),
                },
            )
            results.append(record)

        logger.info(
            "حضور %d مربی در جلسه %s ثبت شد.", len(results), session
        )
        return results

    @classmethod
    @transaction.atomic
    def record_full_session(
        cls,
        session: SessionDate,
        player_data: List[Dict[str, Any]],
        coach_data: List[Dict[str, Any]],
        recorded_by=None,
    ) -> Dict[str, Any]:
        """
        ثبت همزمان حضور بازیکنان و مربیان در یک جلسه.
        ورودی ترکیبی از هر دو لیست.
        """
        players = cls.record_player_attendance(session, player_data, recorded_by)
        coaches = cls.record_coach_attendance(session, coach_data, recorded_by)
        return {"players": players, "coaches": coaches}

    # ── 3. Matrix Builder ───────────────────────────────────────────

    @classmethod
    def build_attendance_matrix(
        cls,
        category: TrainingCategory,
        jalali_month: JalaliMonth,
    ) -> AttendanceMatrixResult:
        """
        ماتریس کامل حضور و غیاب را می‌سازد.
        ردیف‌ها: بازیکنان و مربیان دسته
        ستون‌ها: جلسات ماه
        """
        sheet, _ = cls.get_or_create_sheet(category, jalali_month)

        # ماه آینده ممکن است هنوز شیت نداشته باشد
        if sheet is None:
            return AttendanceMatrixResult(
                sheet=None,
                category=category,
                jalali_month=jalali_month,
                session_dates=[],
                player_rows=[],
                coach_rows=[],
            )

        session_dates = list(
            sheet.session_dates.order_by("date")
        )
        session_ids = [s.pk for s in session_dates]

        # ── بازیکنان ─────────────────────────────────────────────
        players = list(
            category.players.filter(is_archived=False, status="approved")
            .select_related()
            .order_by("last_name", "first_name")
        )

        # یکجا دریافت تمام رکوردهای حضور این ماه
        all_player_att = (
            PlayerAttendance.objects
            .filter(session__sheet=sheet)
            .values("session_id", "player_id", "status")
        )
        player_att_map: Dict[Tuple, str] = {
            (r["session_id"], r["player_id"]): r["status"]
            for r in all_player_att
        }

        player_rows = []
        for player in players:
            row = AttendanceMatrixRow(
                entity_id=player.pk,
                entity_name=f"{player.first_name} {player.last_name}",
                entity_type="player",
                sessions={
                    sid: player_att_map.get(
                        (sid, player.pk), PlayerAttendance.AttendanceStatus.ABSENT
                    )
                    for sid in session_ids
                },
            )
            player_rows.append(row)

        # ── مربیان ───────────────────────────────────────────────
        coaches = list(
            Coach.objects.filter(
                coachcategoryrate__category=category,
                coachcategoryrate__is_active=True,
                is_active=True,
            ).distinct().order_by("last_name")
        )

        all_coach_att = (
            CoachAttendance.objects
            .filter(session__sheet=sheet)
            .values("session_id", "coach_id", "status")
        )
        coach_att_map: Dict[Tuple, str] = {
            (r["session_id"], r["coach_id"]): r["status"]
            for r in all_coach_att
        }

        coach_rows = []
        for coach in coaches:
            row = AttendanceMatrixRow(
                entity_id=coach.pk,
                entity_name=f"{coach.first_name} {coach.last_name}",
                entity_type="coach",
                sessions={
                    sid: coach_att_map.get(
                        (sid, coach.pk), CoachAttendance.AttendanceStatus.ABSENT
                    )
                    for sid in session_ids
                },
            )
            coach_rows.append(row)

        return AttendanceMatrixResult(
            sheet=sheet,
            category=category,
            jalali_month=jalali_month,
            session_dates=session_dates,
            player_rows=player_rows,
            coach_rows=coach_rows,
        )

    # ── 4. Finalization ─────────────────────────────────────────────

    @classmethod
    @transaction.atomic
    def finalize_sheet(
        cls,
        sheet: AttendanceSheet,
        finalized_by,
    ) -> AttendanceSheet:
        """
        نهایی کردن لیست حضور و غیاب.
        پس از نهایی شدن، ویرایش مسدود می‌شود.
        """
        if sheet.is_finalized:
            raise ValueError("این لیست قبلاً نهایی شده است.")

        sheet.is_finalized = True
        sheet.finalized_at = timezone.now()
        sheet.finalized_by = finalized_by
        sheet.save(update_fields=["is_finalized", "finalized_at", "finalized_by"])

        logger.info("لیست %s توسط %s نهایی شد.", sheet, finalized_by)
        return sheet

    # ── 5. Statistics ───────────────────────────────────────────────

    @staticmethod
    def get_player_monthly_stats(
        player: Player,
        jalali_month: JalaliMonth,
    ) -> Dict[str, Any]:
        """آمار حضور یک بازیکن در یک ماه در تمام دسته‌هایش."""
        stats = {}
        for cat in player.categories.filter(is_active=True):
            try:
                sheet = AttendanceSheet.objects.get(
                    category=cat,
                    jalali_year=jalali_month.year,
                    jalali_month=jalali_month.month,
                )
                records = PlayerAttendance.objects.filter(
                    session__sheet=sheet, player=player
                )
                stats[cat.name] = {
                    "present": records.filter(status="present").count(),
                    "absent":  records.filter(status="absent").count(),
                    "excused": records.filter(status="excused").count(),
                    "total":   sheet.session_dates.count(),
                }
            except AttendanceSheet.DoesNotExist:
                stats[cat.name] = None
        return stats