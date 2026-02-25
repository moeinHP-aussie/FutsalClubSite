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
    - اعلان‌های خوانده‌نشده
    - تعداد رسیدهای در انتظار تأیید (برای مدیر مالی)
    - تعداد فاکتورهای معوق (برای بازیکن)
    """
    ctx = {
        "unread_notif_count":   0,
        "recent_notifications": [],
        "pending_receipt_count": 0,  # مدیر مالی
        "player_pending_count":  0,  # بازیکن
    }

    if not request.user.is_authenticated:
        return ctx

    # اعلان‌ها — یک query
    notifications = list(
        Notification.objects
        .filter(recipient=request.user)
        .order_by("-created_at")[:8]
    )
    ctx["recent_notifications"] = notifications
    ctx["unread_notif_count"]    = Notification.objects.filter(
        recipient=request.user, is_read=False
    ).count()

    # رسیدهای در انتظار برای مدیر مالی
    if getattr(request.user, "is_finance_manager", False):
        from futsal_club.models import PlayerInvoice
        ctx["pending_receipt_count"] = PlayerInvoice.objects.filter(
            status=PlayerInvoice.PaymentStatus.PENDING_CONFIRM
        ).count()

    # فاکتورهای معوق برای بازیکن
    if getattr(request.user, "is_player", False):
        try:
            from futsal_club.models import PlayerInvoice
            ctx["player_pending_count"] = PlayerInvoice.objects.filter(
                player=request.user.player_profile,
                status__in=[
                    PlayerInvoice.PaymentStatus.PENDING,
                    PlayerInvoice.PaymentStatus.DEBTOR,
                ],
            ).count()
        except Exception:
            pass

    return ctx