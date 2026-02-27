"""
futsal_club/templatetags/attendance_extras.py
─────────────────────────────────────────────────────────────────────
Template filters و tags مورد نیاز در attendance و payroll templates.

مکان فایل: futsal_club/templatetags/attendance_extras.py
(مطمئن شوید فایل __init__.py در پوشه templatetags وجود دارد)
"""
from django import template

register = template.Library()


@register.filter
def rial_format(value):
    """
    عدد را به فرمت ریال تبدیل می‌کند.
    مثال: 1500000 → ۱٬۵۰۰٬۰۰۰ ریال
    """
    try:
        value = int(value)
        return f"{value:,} ریال"
    except (TypeError, ValueError):
        return "۰ ریال"


@register.filter
def toman_format(value):
    """
    ریال را به تومان تبدیل و فرمت‌بندی می‌کند.
    مثال: 1500000 → ۱۵۰٬۰۰۰ تومان
    """
    try:
        value = int(value) // 10
        return f"{value:,} تومان"
    except (TypeError, ValueError):
        return "۰ تومان"


@register.filter
def attendance_pct_class(pct):
    """
    درصد حضور را به کلاس CSS تبدیل می‌کند.
    مثال: 85 → 'pct-high'
    """
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
    """
    نسبت value به total را به صورت عدد صحیح (0-100) برمی‌گرداند.
    جایگزین ساده‌تر تگ widthratio داخلی جنگو.
    """
    try:
        if not total:
            return 0
        return int(int(value) / int(total) * 100)
    except (TypeError, ValueError, ZeroDivisionError):
        return 0


@register.filter
def jalali_timesince(value):
    """
    تبدیل jdatetime (تاریخ جلالی) به نمایش «چه مدت پیش».
    مشکل: timesince جنگو با jDateTimeField کار نمی‌کند چون
    سال جلالی ۱۴۰۴ را با سال میلادی مقایسه می‌کند.
    
    استفاده: {{ ann.published_at|jalali_timesince }}
    """
    import datetime
    try:
        # jdatetime را به datetime میلادی تبدیل می‌کنیم
        if hasattr(value, 'togregorian'):
            greg = value.togregorian()
            # اگر date باشد نه datetime، به midnight تبدیل می‌کنیم
            if isinstance(greg, datetime.date) and not isinstance(greg, datetime.datetime):
                import pytz
                greg = datetime.datetime.combine(greg, datetime.time.min).replace(tzinfo=pytz.UTC)
            elif isinstance(greg, datetime.datetime) and greg.tzinfo is None:
                import pytz
                greg = greg.replace(tzinfo=pytz.UTC)
        else:
            return ""
        
        now = datetime.datetime.now(tz=datetime.timezone.utc)
        diff = now - greg
        
        seconds = int(diff.total_seconds())
        if seconds < 60:
            return "لحظاتی پیش"
        minutes = seconds // 60
        if minutes < 60:
            return f"{minutes} دقیقه پیش"
        hours = minutes // 60
        if hours < 24:
            return f"{hours} ساعت پیش"
        days = hours // 24
        if days < 7:
            return f"{days} روز پیش"
        weeks = days // 7
        if weeks < 4:
            return f"{weeks} هفته پیش"
        months = days // 30
        if months < 12:
            return f"{months} ماه پیش"
        years = days // 365
        return f"{years} سال پیش"
    except Exception:
        return ""


@register.filter
def jalali_date_short(value):
    """
    نمایش تاریخ جلالی به فرمت کوتاه: ۱۴۰۴/۱۲/۰۲ — ۲۲:۴۰
    استفاده: {{ ann.published_at|jalali_date_short }}
    """
    try:
        if hasattr(value, 'year') and hasattr(value, 'month') and hasattr(value, 'day'):
            if hasattr(value, 'hour'):
                return f"{value.year}/{value.month:02d}/{value.day:02d} — {value.hour:02d}:{value.minute:02d}"
            return f"{value.year}/{value.month:02d}/{value.day:02d}"
        return str(value)
    except Exception:
        return ""


@register.filter
def get_item(dictionary, key):
    """{{ mydict|get_item:key }} — دریافت مقدار از دیکشنری با کلید متغیر."""
    if dictionary is None:
        return None
    return dictionary.get(key)