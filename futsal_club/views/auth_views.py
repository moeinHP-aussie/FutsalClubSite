"""
futsal_club/views/auth_views.py
─────────────────────────────────────────────────────────────────────
احراز هویت: ورود / خروج / داشبورد
"""
from __future__ import annotations

from django.contrib.auth import authenticate, login, logout
from django.contrib.auth.mixins import LoginRequiredMixin
from django.shortcuts import redirect, render
from django.views import View
from django.views.generic import TemplateView

from ..models import CustomUser, Player, TrainingCategory, Notification


class CustomLoginView(View):
    """صفحه ورود با ریدایرکت بر اساس نقش."""
    template_name = "auth/login.html"

    def get(self, request):
        if request.user.is_authenticated:
            return redirect("accounts:dashboard")
        return render(request, self.template_name, {"next": request.GET.get("next", "")})

    def post(self, request):
        username = request.POST.get("username", "").strip()
        password = request.POST.get("password", "")
        next_url = request.POST.get("next", "")

        user = authenticate(request, username=username, password=password)
        if user is None:
            return render(request, self.template_name, {
                "error": "نام کاربری یا رمز عبور اشتباه است.",
                "username": username,
                "next": next_url,
            })

        if not user.is_active:
            return render(request, self.template_name, {
                "error": "حساب کاربری شما غیرفعال است. با مدیر تماس بگیرید.",
            })

        login(request, user)

        if next_url:
            return redirect(next_url)
        return redirect("accounts:dashboard")


class CustomLogoutView(View):
    """خروج از سیستم."""
    def post(self, request):
        logout(request)
        return redirect("accounts:login")

    def get(self, request):
        logout(request)
        return redirect("accounts:login")


class DashboardView(LoginRequiredMixin, TemplateView):
    """
    داشبورد اصلی — بر اساس نقش کاربر، آمار مختلف نشان می‌دهد.
    """
    template_name = "auth/dashboard.html"
    login_url     = "/auth/login/"

    def get_context_data(self, **kwargs):
        ctx  = super().get_context_data(**kwargs)
        user = self.request.user

        ctx["user"] = user

        # ── آمار مدیر فنی ─────────────────────────────────────────
        if user.is_technical_director:
            ctx["total_players"]    = Player.objects.filter(is_archived=False, status="approved").count()
            ctx["pending_players"]  = Player.objects.filter(status="pending", is_archived=False).count()
            ctx["archived_players"] = Player.objects.filter(is_archived=True).count()
            ctx["total_categories"] = TrainingCategory.objects.filter(is_active=True).count()
            ctx["recent_players"]   = (
                Player.objects
                .filter(is_archived=False)
                .order_by("-registration_date")[:5]
            )

            # ── آمار رده‌های سنی ─────────────────────────────────
            from ..models import PlayerChangeLog
            from collections import Counter
            approved_players = Player.objects.filter(status="approved", is_archived=False).exclude(dob__isnull=True)
            age_cat_counts = Counter()
            for p in approved_players:
                age_cat_counts[p.get_age_category()] += 1
            # مرتب‌سازی: زیر 8، زیر 9، ... ، بزرگسال
            def sort_key(item):
                cat = item[0]
                if cat.startswith('زیر '):
                    try: return int(cat.split()[1])
                    except: return 99
                return 100
            total = sum(age_cat_counts.values()) or 1
            ctx["age_category_stats"] = [
                (cat, cnt, round(cnt * 100 / total))
                for cat, cnt in sorted(age_cat_counts.items(), key=sort_key)
            ]

            # ── فید تغییرات اخیر ─────────────────────────────────
            ctx["recent_changes"] = PlayerChangeLog.objects.select_related(
                "player", "changed_by"
            ).order_by("-created_at")[:15]

            # ── اعلان‌های خوانده‌نشده مدیر فنی ──────────────────
            ctx["unread_notifications"] = user.notifications.filter(
                is_read=False
            ).order_by("-created_at")[:10]

        # ── آمار مالی ─────────────────────────────────────────────
        if user.is_finance_manager:
            from ..models import PlayerInvoice, CoachSalary
            ctx["pending_invoices"] = PlayerInvoice.objects.filter(status="pending").count()
            ctx["pending_salaries"] = CoachSalary.objects.filter(status="pending").count()
            ctx["total_debt"]       = (
                PlayerInvoice.objects
                .filter(status="debtor")
                .count()
            )

        # ── آمار مربی ─────────────────────────────────────────────
        if user.is_coach:
            try:
                from ..models import PlayerChangeLog
                coach = user.coach_profile
                ctx["my_categories"] = coach.categories.filter(is_active=True)
                ctx["total_players_coached"] = (
                    Player.objects
                    .filter(categories__in=ctx["my_categories"], is_archived=False)
                    .distinct()
                    .count()
                )
                # تغییرات اخیر بازیکنان مربی
                my_player_ids = Player.objects.filter(
                    categories__in=ctx["my_categories"], is_archived=False
                ).values_list("pk", flat=True)
                ctx["recent_changes"] = PlayerChangeLog.objects.filter(
                    player__pk__in=my_player_ids
                ).select_related("player", "changed_by").order_by("-created_at")[:10]
                ctx["unread_notifications"] = user.notifications.filter(
                    is_read=False
                ).order_by("-created_at")[:8]
            except Exception:
                pass

        # ── آمار بازیکن ───────────────────────────────────────────
        if user.is_player:
            try:
                player = Player.objects.get(user=user, is_archived=False)
                ctx["my_player"] = player
                from ..models import PlayerInvoice
                ctx["my_pending_invoices"] = PlayerInvoice.objects.filter(
                    player=player, status="pending"
                ).count()
            except Player.DoesNotExist:
                pass

        # ── اعلان‌های خوانده‌نشده (همه نقش‌ها) ─────────────────────
        ctx["unread_count"] = Notification.objects.filter(
            recipient=user, is_read=False
        ).count()

        return ctx


class ChangePasswordView(LoginRequiredMixin, View):
    """تغییر رمز عبور."""
    template_name = "auth/password_change.html"
    login_url     = "/auth/login/"

    def get(self, request):
        return render(request, self.template_name)

    def post(self, request):
        old_pw  = request.POST.get("old_password", "")
        new_pw  = request.POST.get("new_password1", "")
        new_pw2 = request.POST.get("new_password2", "")

        if not request.user.check_password(old_pw):
            return render(request, self.template_name, {"error": "رمز فعلی اشتباه است."})
        if new_pw != new_pw2:
            return render(request, self.template_name, {"error": "رمزهای جدید یکسان نیستند."})
        if len(new_pw) < 8:
            return render(request, self.template_name, {"error": "رمز باید حداقل ۸ کاراکتر باشد."})

        request.user.set_password(new_pw)
        request.user.save()
        logout(request)
        return redirect("accounts:login")