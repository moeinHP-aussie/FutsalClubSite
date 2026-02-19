"""
utils/jalali_utils.py
─────────────────────────────────────────────────────────────────────
ابزارهای تاریخ شمسی برای سیستم مدیریت باشگاه فوتسال
All Jalali date helpers used across the attendance and payroll system.
"""

from __future__ import annotations

import calendar
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta
from typing import Iterator, List, Optional, Tuple

import jdatetime


# ─── Weekday mapping ────────────────────────────────────────────────
#  jdatetime: Saturday = 0 … Friday = 6
#  Our TrainingSchedule.Weekday keys → jdatetime integer
WEEKDAY_TO_JDT: dict[str, int] = {
    "sat": 0,
    "sun": 1,
    "mon": 2,
    "tue": 3,
    "wed": 4,
    "thu": 5,
    "fri": 6,
}

JDT_TO_WEEKDAY: dict[int, str] = {v: k for k, v in WEEKDAY_TO_JDT.items()}

WEEKDAY_PERSIAN: dict[str, str] = {
    "sat": "شنبه",
    "sun": "یکشنبه",
    "mon": "دوشنبه",
    "tue": "سه‌شنبه",
    "wed": "چهارشنبه",
    "thu": "پنجشنبه",
    "fri": "جمعه",
}


@dataclass(frozen=True)
class JalaliMonth:
    """نمایش یک ماه شمسی به همراه متدهای کاربردی."""

    year: int
    month: int  # 1–12

    # ── Validation ──────────────────────────────────────────────────
    def __post_init__(self):
        if not (1 <= self.month <= 12):
            raise ValueError(f"ماه باید بین ۱ تا ۱۲ باشد، دریافت شد: {self.month}")

    # ── Boundaries ──────────────────────────────────────────────────
    @property
    def first_day(self) -> jdatetime.date:
        return jdatetime.date(self.year, self.month, 1)

    @property
    def last_day(self) -> jdatetime.date:
        """آخرین روز ماه شمسی (۲۹، ۳۰ یا ۳۱)."""
        return jdatetime.date(self.year, self.month, self.days_in_month)

    @property
    def days_in_month(self) -> int:
        """تعداد روزهای ماه شمسی."""
        if self.month <= 6:
            return 31
        elif self.month <= 11:
            return 30
        else:
            # اسفند: در سال کبیسه ۳۰ روز، غیر کبیسه ۲۹ روز
            return 30 if jdatetime.date(self.year, 1, 1).isleap() else 29

    @property
    def persian_name(self) -> str:
        names = [
            "فروردین", "اردیبهشت", "خرداد",
            "تیر", "مرداد", "شهریور",
            "مهر", "آبان", "آذر",
            "دی", "بهمن", "اسفند",
        ]
        return names[self.month - 1]

    # ── Navigation ──────────────────────────────────────────────────
    @property
    def next_month(self) -> "JalaliMonth":
        if self.month == 12:
            return JalaliMonth(self.year + 1, 1)
        return JalaliMonth(self.year, self.month + 1)

    @property
    def prev_month(self) -> "JalaliMonth":
        if self.month == 1:
            return JalaliMonth(self.year - 1, 12)
        return JalaliMonth(self.year, self.month - 1)

    # ── Iteration ───────────────────────────────────────────────────
    def all_days(self) -> Iterator[jdatetime.date]:
        """یک به یک روزهای ماه را برمی‌گرداند."""
        for d in range(1, self.days_in_month + 1):
            yield jdatetime.date(self.year, self.month, d)

    def days_for_weekdays(self, weekdays: List[str]) -> List[jdatetime.date]:
        """
        تمام روزهایی از این ماه را برمی‌گرداند که در روزهای هفته مشخص‌شده قرار دارند.
        weekdays: لیستی از کلیدهای WEEKDAY_TO_JDT (sat, sun, mon, …)
        """
        target_ints = {WEEKDAY_TO_JDT[w] for w in weekdays if w in WEEKDAY_TO_JDT}
        return [d for d in self.all_days() if d.weekday() in target_ints]

    # ── Conversion ──────────────────────────────────────────────────
    @classmethod
    def current(cls) -> "JalaliMonth":
        today = jdatetime.date.today()
        return cls(today.year, today.month)

    @classmethod
    def from_jdate(cls, d: jdatetime.date) -> "JalaliMonth":
        return cls(d.year, d.month)

    def gregorian_range(self) -> Tuple[date, date]:
        """برگرداندن بازه میلادی معادل این ماه شمسی."""
        return (
            self.first_day.togregorian(),
            self.last_day.togregorian(),
        )

    def __str__(self) -> str:
        return f"{self.year}/{self.month:02d} ({self.persian_name})"


# ─── Standalone helpers ─────────────────────────────────────────────

def today_jalali() -> jdatetime.date:
    return jdatetime.date.today()


def now_jalali() -> jdatetime.datetime:
    return jdatetime.datetime.now()


def gregorian_to_jalali(d: date) -> jdatetime.date:
    return jdatetime.date.fromgregorian(date=d)


def jalali_to_gregorian(d: jdatetime.date) -> date:
    return d.togregorian()


def jalali_date_display(d: Optional[jdatetime.date]) -> str:
    """نمایش فارسی تاریخ شمسی؛ در صورت None بودن خط تیره برمی‌گرداند."""
    if d is None:
        return "—"
    return f"{d.year}/{d.month:02d}/{d.day:02d}"


def parse_jalali_month_from_request(year: Optional[str], month: Optional[str]) -> JalaliMonth:
    """
    تبدیل پارامترهای رشته‌ای year/month از request به JalaliMonth.
    در صورت عدم وجود، ماه جاری را برمی‌گرداند.
    """
    try:
        y = int(year)
        m = int(month)
        return JalaliMonth(y, m)
    except (TypeError, ValueError):
        return JalaliMonth.current()


def insurance_expiry_in_days(expiry: jdatetime.date) -> int:
    """تعداد روز تا انقضای بیمه (منفی = منقضی شده)."""
    today = jdatetime.date.today()
    delta = expiry.togregorian() - today.togregorian()
    return delta.days
