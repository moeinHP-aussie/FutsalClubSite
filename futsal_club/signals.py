"""
signals.py
─────────────────────────────────────────────────────────────────────
سیگنال‌های جنگو برای اعلان‌های خودکار
Auto-notification signals: insurance expiry, player approval, etc.

در apps.py ثبت کنید:
    class FutsalClubConfig(AppConfig):
        def ready(self):
            import futsal_club.signals  # noqa: F401
"""
from __future__ import annotations

import logging

from django.db.models.signals import post_save, pre_save
from django.dispatch import receiver
from django.utils import timezone

from .models import CustomUser, Notification, Player

logger = logging.getLogger(__name__)


# ────────────────────────────────────────────────────────────────────
#  Signal 1: بازیکن تأیید/رد شد → اعلان
# ────────────────────────────────────────────────────────────────────

@receiver(pre_save, sender=Player)
def _cache_old_status(sender, instance, **kwargs):
    """وضعیت قبلی را قبل از ذخیره در حافظه نگه می‌دارد."""
    if instance.pk:
        try:
            instance._old_status = Player.objects.values_list(
                "status", flat=True
            ).get(pk=instance.pk)
        except Player.DoesNotExist:
            instance._old_status = None
    else:
        instance._old_status = None


@receiver(post_save, sender=Player)
def on_player_status_change(sender, instance: Player, created: bool, **kwargs):
    """
    وقتی وضعیت بازیکن تغییر می‌کند:
    - تأیید → اعلان به بازیکن
    - بیمه فعال شد → بررسی تاریخ انقضا
    """
    if created:
        return

    old = getattr(instance, "_old_status", None)
    new = instance.status

    # وضعیت تغییر نکرده
    if old == new:
        return

    # ── تأیید شد ────────────────────────────────────────────────
    if new == Player.Status.APPROVED and old != Player.Status.APPROVED:
        if instance.user:
            Notification.objects.get_or_create(
                recipient      = instance.user,
                type           = Notification.NotificationType.GENERAL,
                title          = "✅ ثبت‌نام تأیید شد",
                defaults={
                    "message": (
                        f"عزیز {instance.first_name}، "
                        "ثبت‌نام شما در باشگاه فوتسال تأیید شد. "
                        "می‌توانید اکنون وارد سیستم شوید."
                    ),
                    "related_player": instance,
                }
            )

    # ── بیمه به‌روز شد → بررسی انقضا ─────────────────────────
    if instance.insurance_status == "active" and instance.insurance_expiry_date:
        _check_insurance_for_player(instance)


# ────────────────────────────────────────────────────────────────────
#  Signal 2: بیمه در حال انقضاست
# ────────────────────────────────────────────────────────────────────

def _check_insurance_for_player(player: Player, warn_days: int = 30):
    """
    اعلان انقضای بیمه به بازیکن، مربیان دسته، و مدیران فنی.
    فقط اگر بیمه ظرف warn_days روز منقضی می‌شود.
    """
    import jdatetime
    if not player.insurance_expiry_date:
        return

    today = jdatetime.date.today()
    try:
        expiry_greg = player.insurance_expiry_date.togregorian()
        today_greg  = today.togregorian()
        days_left   = (expiry_greg - today_greg).days
    except Exception:
        return

    if days_left > warn_days or days_left < 0:
        return   # منقضی شده یا فاصله کافی دارد

    _send_insurance_notifications(player, days_left)


def _send_insurance_notifications(player: Player, days_left: int):
    """ارسال اعلان انقضای بیمه به ذینفعان."""

    if days_left <= 0:
        urgency = "❌ بیمه منقضی شده"
        msg_prefix = f"بیمه بازیکن {player.first_name} {player.last_name} منقضی شده است."
    elif days_left <= 7:
        urgency = "🚨 فوری: انقضای بیمه"
        msg_prefix = (
            f"بیمه بازیکن {player.first_name} {player.last_name} "
            f"تنها {days_left} روز دیگر منقضی می‌شود!"
        )
    else:
        urgency = "⚠️ هشدار انقضای بیمه"
        msg_prefix = (
            f"بیمه بازیکن {player.first_name} {player.last_name} "
            f"ظرف {days_left} روز آینده منقضی می‌شود."
        )

    full_msg = f"{msg_prefix}\nکد بازیکن: {player.player_id}"

    recipients = set()

    # ── اعلان به بازیکن ──────────────────────────────────────────
    if player.user:
        recipients.add(player.user.pk)
        Notification.objects.update_or_create(
            recipient      = player.user,
            type           = Notification.NotificationType.INSURANCE_EXPIRY,
            defaults={
                "title":          f"بیمه شما: {urgency}",
                "message":        f"بیمه‌نامه شما ظرف {days_left} روز منقضی می‌شود. لطفاً اقدام کنید.",
                "is_read":        False,
                "related_player": player,
            }
        )

    # ── اعلان به مربیان دسته ─────────────────────────────────────
    from .models import CoachCategoryRate
    coach_users = (
        CoachCategoryRate.objects
        .filter(category__in=player.categories.all(), is_active=True)
        .select_related("coach__user")
        .values_list("coach__user", flat=True)
        .distinct()
    )
    for uid in coach_users:
        if uid and uid not in recipients:
            recipients.add(uid)
            try:
                user = CustomUser.objects.get(pk=uid, is_active=True)
                Notification.objects.update_or_create(
                    recipient      = user,
                    type           = Notification.NotificationType.INSURANCE_EXPIRY,
                    related_player = player,
                    defaults={
                        "title":   urgency,
                        "message": full_msg,
                        "is_read": False,
                    }
                )
            except CustomUser.DoesNotExist:
                pass

    # ── اعلان به مدیران فنی ─────────────────────────────────────
    directors = CustomUser.objects.filter(is_technical_director=True, is_active=True)
    for td in directors:
        if td.pk not in recipients:
            Notification.objects.update_or_create(
                recipient      = td,
                type           = Notification.NotificationType.INSURANCE_EXPIRY,
                related_player = player,
                defaults={
                    "title":   urgency,
                    "message": full_msg,
                    "is_read": False,
                }
            )

    logger.info("اعلان بیمه ارسال شد: %s — %d روز باقی‌مانده", player, days_left)


# ────────────────────────────────────────────────────────────────────
#  Service Function (قابل فراخوانی از تسک Celery)
# ────────────────────────────────────────────────────────────────────

def run_insurance_expiry_check(warn_days: int = 30) -> dict:
    """
    بررسی دستی/برنامه‌ریزی‌شده برای تمام بازیکنان فعال.
    از tasks.py فراخوانی می‌شود.

    Returns: {"checked": N, "notified": N}
    """
    players = Player.objects.filter(
        status=Player.Status.APPROVED,
        is_archived=False,
        insurance_status="active",
    ).exclude(insurance_expiry_date__isnull=True)

    checked = 0
    notified = 0

    for player in players:
        checked += 1
        import jdatetime
        try:
            expiry_greg = player.insurance_expiry_date.togregorian()
            days_left   = (expiry_greg - jdatetime.date.today().togregorian()).days
        except Exception:
            continue

        if days_left <= warn_days:
            _send_insurance_notifications(player, days_left)
            notified += 1

    logger.info(
        "[بررسی بیمه] بازیکن بررسی‌شده: %d | اعلان ارسال‌شده: %d",
        checked, notified
    )
    return {"checked": checked, "notified": notified}
