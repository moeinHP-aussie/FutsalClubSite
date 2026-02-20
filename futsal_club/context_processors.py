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
        qs = Notification.objects.filter(
            recipient=request.user
        ).order_by("-created_at")

        ctx["unread_notif_count"]   = qs.filter(is_read=False).count()
        ctx["recent_notifications"] = list(qs[:8])

    return ctx