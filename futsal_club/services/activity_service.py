"""
futsal_club/services/activity_service.py
────────────────────────────────────────────────────────────────
سرویس ثبت لاگ تغییرات بازیکن + ارسال اعلان به مربیان/مدیر فنی
"""
from __future__ import annotations
import logging
from typing import Optional

logger = logging.getLogger(__name__)


def log_player_change(
    player,
    actor,
    action: str,
    detail: str = "",
    notify_coaches: bool = True,
    notify_td: bool = True,
) -> None:
    """
    ثبت لاگ تغییر برای بازیکن + ارسال اعلان به مربیان و مدیر فنی.

    Parameters
    ----------
    player  : Player instance
    actor   : CustomUser who made the change
    action  : PlayerActivityLog.ActionType value
    detail  : human-readable description of what changed
    notify_coaches : ارسال اعلان به مربیان دسته‌های بازیکن
    notify_td      : ارسال اعلان به تمام مدیران فنی
    """
    from ..models import PlayerActivityLog, Notification, CustomUser

    # 1 — ثبت لاگ
    try:
        PlayerActivityLog.objects.create(
            player=player,
            actor=actor,
            action=action,
            detail=detail or action,
        )
    except Exception as e:
        logger.error("Failed to create activity log: %s", e)
        return

    # 2 — متن اعلان
    actor_name = (
        f"{actor.first_name} {actor.last_name}".strip()
        if actor else "سیستم"
    )
    action_label = dict(PlayerActivityLog.ActionType.choices).get(action, action)
    title   = f"تغییر در پروفایل {player.first_name} {player.last_name}"
    message = (
        f"{actor_name} تغییری در پروفایل «{player.first_name} {player.last_name}» "
        f"ایجاد کرد: {action_label}"
        + (f"\n{detail}" if detail else "")
    )

    recipients = set()

    # 3 — مربیان دسته‌های بازیکن (به‌جز خود actor)
    if notify_coaches:
        try:
            for cat in player.categories.filter(is_active=True):
                for rate in cat.coach_rates.filter(is_active=True).select_related("coach__user"):
                    if rate.coach.user and rate.coach.user != actor:
                        recipients.add(rate.coach.user)
        except Exception as e:
            logger.warning("Could not get coach recipients: %s", e)

    # 4 — مدیران فنی (به‌جز خود actor)
    if notify_td:
        try:
            for td_user in CustomUser.objects.filter(is_technical_director=True, is_active=True):
                if td_user != actor:
                    recipients.add(td_user)
        except Exception as e:
            logger.warning("Could not get TD recipients: %s", e)

    # 5 — ارسال اعلان‌ها
    notifs = [
        Notification(
            recipient=user,
            type=Notification.NotificationType.GENERAL,
            title=title,
            message=message,
            related_player=player,
        )
        for user in recipients
    ]
    if notifs:
        try:
            Notification.objects.bulk_create(notifs, ignore_conflicts=True)
        except Exception as e:
            logger.error("Failed to create notifications: %s", e)
