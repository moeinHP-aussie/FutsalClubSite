"""
futsal_club/templatetags/attendance_extras.py
─────────────────────────────────────────────────────────────────────
Custom template tags and filters for the attendance + payroll system.

مکان فایل: futsal_club/templatetags/attendance_extras.py
(فایل __init__.py هم باید در همین پوشه باشد)
"""
from django import template

register = template.Library()


# ──────────────────────────────────────────────────────────────────
# فیلترهای اصلی (نسخه اولیه پروژه)
# ──────────────────────────────────────────────────────────────────

@register.filter
def get_item(dictionary, key):
    """
    دسترسی به مقدار دیکشنری در template با کلید متغیر.
    استفاده: {{ my_dict|get_item:key_var }}
    کاربرد اصلی: ماتریس حضور و غیاب
    """
    if isinstance(dictionary, dict):
        return dictionary.get(key, "absent")
    return "absent"


@register.filter
def persian_number(value):
    """تبدیل اعداد لاتین به فارسی."""
    PERSIAN_DIGITS = "۰۱۲۳۴۵۶۷۸۹"
    return "".join(
        PERSIAN_DIGITS[int(c)] if c.isdigit() else c
        for c in str(value)
    )


@register.filter
def rial_format(value):
    """
    نمایش مبلغ با جداکننده هزار و واحد ریال.
    مثال: 1500000 → 1,500,000 ریال
    """
    try:
        return f"{int(value):,} ریال"
    except (TypeError, ValueError):
        return "0 ریال"


@register.simple_tag
def attendance_cell_class(status: str) -> str:
    """کلاس CSS متناسب با وضعیت حضور (برای ماتریس)."""
    mapping = {
        "present": "cell-present",
        "absent":  "cell-absent",
        "excused": "cell-excused",
    }
    return mapping.get(status, "cell-absent")


@register.inclusion_tag("attendance/partials/status_badge.html")
def status_badge(status: str):
    """رندر partial badge برای وضعیت حضور."""
    labels = {
        "present": ("حاضر", "#d3f9d8", "#2f9e44"),
        "absent":  ("غایب", "#ffe3e3", "#e03131"),
        "excused": ("موجه", "#fff3bf", "#f08c00"),
    }
    label, bg, color = labels.get(status, ("نامشخص", "#f1f3f5", "#868e96"))
    return {"label": label, "bg": bg, "color": color}


# ──────────────────────────────────────────────────────────────────
# فیلترهای اضافه‌شده برای payroll templates
# ──────────────────────────────────────────────────────────────────

@register.filter
def toman_format(value):
    """تبدیل ریال به تومان با فرمت‌بندی."""
    try:
        return f"{int(value) // 10:,} تومان"
    except (TypeError, ValueError):
        return "0 تومان"


@register.filter
def attendance_pct_class(pct):
    """تبدیل درصد حضور به کلاس CSS: pct-high / pct-mid / pct-low"""
    try:
        pct = float(pct)
        if pct >= 75:
            return "pct-high"
        elif pct >= 50:
            return "pct-mid"
        return "pct-low"
    except (TypeError, ValueError):
        return "pct-low"


@register.filter
def widthratio_int(value, total):
    """نسبت value به total را به عدد صحیح 0-100 تبدیل می‌کند."""
    try:
        if not total:
            return 0
        return int(int(value) / int(total) * 100)
    except (TypeError, ValueError, ZeroDivisionError):
        return 0