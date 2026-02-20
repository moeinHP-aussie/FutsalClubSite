"""
context_processors.py
─────────────────────────────────────────────────────────────────────
Context processors: inject global data into every template.
Add to TEMPLATES[0]['OPTIONS']['context_processors'] in settings.py:
    "futsal_club.context_processors.global_context"
"""
from __future__ import annotations
from futsal_club.models import Notification


def global_context(request):
    """
    داده‌های مورد نیاز در تمام تمپلیت‌ها:
    - اعلان‌های خوانده‌نشده برای نوار کناری
    - تعداد اعلان‌های خوانده‌نشده برای badge
    """
    ctx = {
        "unread_notif_count": 0,
        "recent_notifications": [],
    }

    if request.user.is_authenticated:
        # ✅ اصلاح: یک query به جای دو query — اعلان‌ها رو یکبار می‌گیریم
        notifications = list(
            Notification.objects
            .filter(recipient=request.user)
            .order_by("-created_at")[:8]
        )
        ctx["recent_notifications"] = notifications
        # count از دیتابیس بگیر (ارزان‌تر از شمارش لیست که max 8 تاست)
        ctx["unread_notif_count"] = Notification.objects.filter(
            recipient=request.user, is_read=False
        ).count()

    return ctx