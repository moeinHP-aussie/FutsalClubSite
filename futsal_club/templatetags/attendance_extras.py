"""
templatetags/attendance_extras.py
─────────────────────────────────────────────────────────────────────
Custom template tags and filters for the attendance system.
"""
from django import template

register = template.Library()


@register.filter
def get_item(dictionary, key):
    """
    برای دسترسی به مقدار دیکشنری در تمپلیت با کلید متغیر.
    استفاده: {{ my_dict|get_item:key_var }}
    """
    if isinstance(dictionary, dict):
        return dictionary.get(key, "absent")
    return "absent"


@register.filter
def persian_number(value):
    """تبدیل عدد لاتین به فارسی."""
    PERSIAN_DIGITS = "۰۱۲۳۴۵۶۷۸۹"
    return "".join(PERSIAN_DIGITS[int(c)] if c.isdigit() else c for c in str(value))


@register.filter
def rial_format(value):
    """نمایش مبلغ با جداکننده هزار و واحد ریال."""
    try:
        return f"{int(value):,} ریال"
    except (TypeError, ValueError):
        return value


@register.simple_tag
def attendance_cell_class(status: str) -> str:
    """کلاس CSS برای وضعیت حضور."""
    mapping = {
        "present": "cell-present",
        "absent":  "cell-absent",
        "excused": "cell-excused",
    }
    return mapping.get(status, "cell-absent")


@register.inclusion_tag("attendance/partials/status_badge.html")
def status_badge(status: str):
    labels = {
        "present": ("حاضر",    "#d3f9d8", "#2f9e44"),
        "absent":  ("غایب",    "#ffe3e3", "#e03131"),
        "excused": ("موجه",    "#fff3bf", "#f08c00"),
    }
    label, bg, color = labels.get(status, ("نامشخص", "#f1f3f5", "#868e96"))
    return {"label": label, "bg": bg, "color": color}
