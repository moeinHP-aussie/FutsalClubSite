"""
futsal_club/views/organize_views.py
─────────────────────────────────────────────────────────────────────
سازماندهی رده‌ها — مدیر فنی
شامل:
  - OrganizeView: صفحه اصلی drag-and-drop
  - PlayerMoveView: AJAX endpoint برای جابجایی بازیکن بین دسته‌ها
  - StatsView: صفحه آمارگیری
"""
from __future__ import annotations

import json
from datetime import date

from django.contrib import messages
from django.contrib.auth.mixins import LoginRequiredMixin
from django.db.models import Count, Q
from django.http import JsonResponse
from django.views import View
from django.views.generic import TemplateView

import jdatetime

from ..mixins import RoleRequiredMixin
from ..models import Player, TrainingCategory, TechnicalProfile


# ──────────────────────────────────────────────────────────────────
#  helpers
# ──────────────────────────────────────────────────────────────────
def _player_card_data(player: Player) -> dict:
    """بازیکن را به dict قابل JSON تبدیل می‌کند."""
    tp = getattr(player, "technical_profile", None)
    try:
        age_cat = player.get_age_category()
    except Exception:
        age_cat = "نامشخص"

    # محاسبه سن
    try:
        today = jdatetime.date.today().togregorian()
        dob_g = player.dob.togregorian() if player.dob else None
        age   = (today - dob_g).days // 365 if dob_g else None
    except Exception:
        age = None

    # بررسی بیمه
    ins_expiring = player.is_insurance_expiring_soon(30) if player.insurance_status == "active" else False
    ins_expired  = (player.insurance_status != "active")

    return {
        "id":           player.pk,
        "name":         f"{player.first_name} {player.last_name}",
        "player_id":    player.player_id,
        "age":          age,
        "age_category": str(age_cat),
        "foot":         player.get_preferred_foot_display(),
        "foot_val":     player.preferred_foot,
        "position":     tp.get_position_display() if tp else "—",
        "position_val": tp.position if tp else "-",
        "skill_level":  tp.skill_level if tp else "",
        "insurance":    player.insurance_status,
        "ins_expiring": ins_expiring,
        "ins_expired":  ins_expired,
        "national_id":  player.national_id,
    }


def _category_data(cat: TrainingCategory) -> dict:
    players_qs = cat.players.filter(
        status="approved", is_archived=False
    ).prefetch_related("technical_profile")
    return {
        "id":       cat.pk,
        "name":     cat.name,
        "fee":      int(cat.monthly_fee),
        "players":  [_player_card_data(p) for p in players_qs],
        "count":    players_qs.count(),
        "schedules": [
            f"{s.get_weekday_display()} {s.start_time.strftime('%H:%M')}"
            for s in cat.schedules.all()
        ],
    }


# ──────────────────────────────────────────────────────────────────
#  صفحه سازماندهی رده‌ها
# ──────────────────────────────────────────────────────────────────
class OrganizeView(LoginRequiredMixin, RoleRequiredMixin, TemplateView):
    template_name = "training/organize.html"
    allowed_roles = ["is_technical_director"]

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        cats = TrainingCategory.objects.filter(
            is_active=True
        ).prefetch_related("players__technical_profile", "schedules").order_by("name")

        ctx["categories_json"] = json.dumps(
            [_category_data(c) for c in cats],
            ensure_ascii=False,
        )
        ctx["categories"] = cats

        # بازیکنان بدون دسته
        no_cat = Player.objects.filter(
            status="approved", is_archived=False
        ).exclude(
            categories__in=cats
        ).prefetch_related("technical_profile")

        ctx["unassigned_json"] = json.dumps(
            [_player_card_data(p) for p in no_cat],
            ensure_ascii=False,
        )
        return ctx


# ──────────────────────────────────────────────────────────────────
#  AJAX: جابجایی بازیکن
# ──────────────────────────────────────────────────────────────────
class PlayerMoveView(LoginRequiredMixin, RoleRequiredMixin, View):
    """
    POST /training/organize/move/
    body JSON: { player_id, from_cat, to_cat }
      - from_cat=null → از بدون دسته
      - to_cat=null   → به بدون دسته (حذف از همه)
    """
    allowed_roles = ["is_technical_director"]
    http_method_names = ["post"]

    def post(self, request):
        try:
            data     = json.loads(request.body)
            pid      = int(data["player_id"])
            from_cat = data.get("from_cat")   # int or null
            to_cat   = data.get("to_cat")     # int or null
        except (KeyError, ValueError, json.JSONDecodeError) as e:
            return JsonResponse({"ok": False, "error": str(e)}, status=400)

        player = Player.objects.filter(pk=pid, status="approved", is_archived=False).first()
        if not player:
            return JsonResponse({"ok": False, "error": "بازیکن یافت نشد"}, status=404)

        if from_cat:
            cat = TrainingCategory.objects.filter(pk=from_cat).first()
            if cat:
                cat.players.remove(player)

        if to_cat:
            cat = TrainingCategory.objects.filter(pk=to_cat, is_active=True).first()
            if not cat:
                return JsonResponse({"ok": False, "error": "دسته مقصد یافت نشد"}, status=404)
            cat.players.add(player)

        return JsonResponse({
            "ok":    True,
            "player": _player_card_data(player),
        })


# ──────────────────────────────────────────────────────────────────
#  صفحه آمارگیری
# ──────────────────────────────────────────────────────────────────
class StatsView(LoginRequiredMixin, RoleRequiredMixin, TemplateView):
    template_name = "training/stats.html"
    allowed_roles = ["is_technical_director", "is_coach", "is_finance_manager"]

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)

        approved = Player.objects.filter(status="approved", is_archived=False)

        # ── آمار کلی ─────────────────────────────────────────────
        ctx["total_players"]   = approved.count()
        ctx["total_approved"]  = approved.count()
        ctx["total_pending"]   = Player.objects.filter(status="pending",  is_archived=False).count()
        ctx["total_rejected"]  = Player.objects.filter(status="rejected", is_archived=False).count()
        ctx["total_archived"]  = Player.objects.filter(is_archived=True).count()

        # ── بیمه ─────────────────────────────────────────────────
        ctx["ins_active"]   = approved.filter(insurance_status="active").count()
        ctx["ins_none"]     = approved.filter(insurance_status="none").count()

        today_g = date.today()
        import jdatetime as jdt
        today_j = jdt.date.today()

        # منقضی‌شده
        expired_count = 0
        expiring_count = 0
        for p in approved.filter(insurance_status="active").exclude(insurance_expiry_date__isnull=True):
            try:
                exp_g = p.insurance_expiry_date.togregorian()
                diff  = (exp_g - today_g).days
                if diff < 0:
                    expired_count += 1
                elif diff <= 30:
                    expiring_count += 1
            except Exception:
                pass
        ctx["ins_expired"]  = expired_count
        ctx["ins_expiring"] = expiring_count  # کمتر از ۳۰ روز

        # ── پای غالب ─────────────────────────────────────────────
        ctx["foot_right"] = approved.filter(preferred_foot="R").count()
        ctx["foot_left"]  = approved.filter(preferred_foot="L").count()

        # ── پست ──────────────────────────────────────────────────
        tp_qs = TechnicalProfile.objects.filter(
            player__status="approved", player__is_archived=False
        )
        ctx["pos_gk"]     = tp_qs.filter(position="gk").count()
        ctx["pos_pivot"]  = tp_qs.filter(position="pivot").count()
        ctx["pos_winger"] = tp_qs.filter(position="winger").count()
        ctx["pos_fixo"]   = tp_qs.filter(position="fixo").count()
        ctx["pos_none"]   = tp_qs.filter(position="-").count()
        ctx["no_techprofile"] = approved.count() - tp_qs.count()

        # ── رده سنی ──────────────────────────────────────────────
        # محاسبه سن بر اساس ۱۱ دی ماه سال جاری
        ref = jdt.date(today_j.year, 10, 11).togregorian()
        age_buckets = {
            "زیر ۸":      0,
            "۸-۱۰":       0,
            "۱۱-۱۲":      0,
            "۱۳-۱۴":      0,
            "۱۵-۱۷":      0,
            "۱۸-۲۱":      0,
            "بالای ۲۱":   0,
            "نامشخص":     0,
        }
        ctx["under_16"]   = 0
        ctx["under_14"]   = 0

        for p in approved.exclude(dob__isnull=True):
            try:
                birth_g = p.dob.togregorian()
                age = ref.year - birth_g.year
                if (birth_g.month, birth_g.day) > (ref.month, ref.day):
                    age -= 1
                if age < 8:         age_buckets["زیر ۸"]    += 1
                elif age <= 10:     age_buckets["۸-۱۰"]     += 1
                elif age <= 12:     age_buckets["۱۱-۱۲"]    += 1
                elif age <= 14:     age_buckets["۱۳-۱۴"]    += 1; ctx["under_14"] += 1; ctx["under_16"] += 1
                elif age <= 17:     age_buckets["۱۵-۱۷"]    += 1; ctx["under_16"] += 1
                elif age <= 21:     age_buckets["۱۸-۲۱"]    += 1
                else:               age_buckets["بالای ۲۱"] += 1
            except Exception:
                age_buckets["نامشخص"] += 1
        ctx["age_buckets"] = age_buckets
        ctx["no_dob"]      = approved.filter(dob__isnull=True).count()

        # ── سطح مهارت ────────────────────────────────────────────
        skill_counts = {}
        for level in ["A", "B", "C", "D", "E", "F"]:
            skill_counts[level] = tp_qs.filter(skill_level=level).count()
        skill_counts["نامشخص"] = tp_qs.filter(skill_level="").count()
        ctx["skill_counts"] = skill_counts

        # ── آمار دسته‌ها ──────────────────────────────────────────
        cats = TrainingCategory.objects.filter(is_active=True).annotate(
            pc=Count("players", filter=Q(players__status="approved", players__is_archived=False))
        ).order_by("name")
        ctx["category_stats"] = cats
        ctx["unassigned_count"] = approved.filter(categories__isnull=True).count()

        # همه آمارها را به JSON هم بده (برای charts)
        ctx["charts_data"] = {
            "age":      [[k, v] for k, v in age_buckets.items() if v > 0],
            "foot":     [["راست", ctx["foot_right"]], ["چپ", ctx["foot_left"]]],
            "position": [
                ["دروازه‌بان", ctx["pos_gk"]],
                ["پیوت",       ctx["pos_pivot"]],
                ["وینگر",      ctx["pos_winger"]],
                ["فیکسو",      ctx["pos_fixo"]],
                ["نامشخص",     ctx["pos_none"]],
            ],
            "insurance": [
                ["بیمه فعال",  ctx["ins_active"]],
                ["بدون بیمه",  ctx["ins_none"]],
                ["در حال انقضا", ctx["ins_expiring"]],
                ["منقضی‌شده",  ctx["ins_expired"]],
            ],
            "categories": [[c.name, c.pc] for c in cats],
        }
        ctx["pending_stats"] = [
            ("تأیید شده",  ctx["total_approved"],  "#d1fae5"),
            ("در انتظار",  ctx["total_pending"],   "#fef3c7"),
            ("رد شده",     ctx["total_rejected"],  "#fee2e2"),
            ("آرشیو شده",  ctx["total_archived"],  "#f1f5f9"),
        ]

        import json
        ctx["charts_json"] = json.dumps(ctx["charts_data"], ensure_ascii=False)
        return ctx