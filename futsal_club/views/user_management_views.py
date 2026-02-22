"""
futsal_club/views/user_management_views.py
═══════════════════════════════════════════════════════════════════════
پنل مدیریت کاربران — فقط superuser
شامل:
  • لیست و جستجوی همه کاربران
  • ایجاد مربی / مدیر فنی / مدیر مالی
  • ویرایش نقش‌ها و ریست رمز عبور
  • Provision دسته‌جمعی حساب بازیکنان (username=کد ملی, password=کد ملی)
  • دانلود گزارش اعتبارنامه‌ها به صورت CSV
"""
from __future__ import annotations

import csv
import logging
import secrets
import string
from io import StringIO

from django.contrib import messages
from django.contrib.auth.mixins import LoginRequiredMixin
from django.core.exceptions import PermissionDenied
from django.core.paginator import Paginator
from django.db import transaction
from django.db.models import Q
from django.http import HttpResponse, JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.views import View
from django.views.generic import TemplateView

from ..models import Coach, CustomUser, Player

logger = logging.getLogger(__name__)


class SuperuserRequiredMixin:
    def dispatch(self, request, *args, **kwargs):
        if not request.user.is_authenticated or not request.user.is_superuser:
            raise PermissionDenied
        return super().dispatch(request, *args, **kwargs)


# ── helpers ───────────────────────────────────────────────────────

def _make_password(raw: str) -> str:
    """رمز عبور از کد ملی / شماره موبایل"""
    return raw  # Django set_password hashing handles the rest


def _unique_username(base: str) -> str:
    """اگر username تکراری بود، عدد اضافه کن"""
    username = base
    counter  = 1
    while CustomUser.objects.filter(username=username).exists():
        username = f"{base}_{counter}"
        counter += 1
    return username


# ══════════════════════════════════════════════════════════════════
#  1. لیست کاربران
# ══════════════════════════════════════════════════════════════════

class UserListView(SuperuserRequiredMixin, LoginRequiredMixin, TemplateView):
    template_name = "admin_panel/user_list.html"

    def get(self, request, *args, **kwargs):
        q    = request.GET.get("q", "").strip()
        role = request.GET.get("role", "")

        qs = CustomUser.objects.all().order_by("last_name", "first_name", "username")

        if q:
            qs = qs.filter(
                Q(username__icontains=q) |
                Q(first_name__icontains=q) |
                Q(last_name__icontains=q)
            )

        if role == "player":
            qs = qs.filter(is_player=True)
        elif role == "coach":
            qs = qs.filter(is_coach=True)
        elif role == "td":
            qs = qs.filter(is_technical_director=True)
        elif role == "finance":
            qs = qs.filter(is_finance_manager=True)
        elif role == "superuser":
            qs = qs.filter(is_superuser=True)
        elif role == "no_player_link":
            # بازیکنانی که is_player=True ولی Player record ندارن
            linked_ids = Player.objects.exclude(user=None).values_list("user_id", flat=True)
            qs = qs.filter(is_player=True).exclude(pk__in=linked_ids)

        paginator   = Paginator(qs, 40)
        page_obj    = paginator.get_page(request.GET.get("page", 1))

        # آمار
        stats = {
            "total":      CustomUser.objects.count(),
            "players":    CustomUser.objects.filter(is_player=True).count(),
            "coaches":    CustomUser.objects.filter(is_coach=True).count(),
            "staff":      CustomUser.objects.filter(
                            Q(is_technical_director=True) | Q(is_finance_manager=True)
                          ).count(),
            "inactive":   CustomUser.objects.filter(is_active=False).count(),
            "no_account": Player.objects.filter(
                            status="approved", is_archived=False, user__isnull=True
                          ).count(),
        }

        return render(request, self.template_name, {
            "page_obj": page_obj,
            "q": q,
            "role": role,
            "stats": stats,
        })


# ══════════════════════════════════════════════════════════════════
#  2. ایجاد کاربر staff (مربی / مدیر فنی / مدیر مالی)
# ══════════════════════════════════════════════════════════════════

class UserCreateView(SuperuserRequiredMixin, LoginRequiredMixin, View):
    template_name = "admin_panel/user_create.html"

    def get(self, request):
        roles = [
            ("technical_director", "مدیر فنی",    "🔧"),
            ("finance_manager",    "مدیر مالی",   "💰"),
            ("coach",              "مربی",         "🎯"),
            ("superuser",          "ادمین دیگر",   "👑"),
        ]
        return render(request, self.template_name, {"roles": roles})

    @transaction.atomic
    def post(self, request):
        username  = request.POST.get("username", "").strip()
        password  = request.POST.get("password", "").strip()
        first     = request.POST.get("first_name", "").strip()
        last      = request.POST.get("last_name", "").strip()
        role      = request.POST.get("role", "")
        phone     = request.POST.get("phone", "").strip()
        # coach extras
        coach_degree = request.POST.get("degree", "")

        errors = []
        if not username:
            errors.append("نام کاربری الزامی است")
        if not password or len(password) < 6:
            errors.append("رمز عبور باید حداقل ۶ کاراکتر باشد")
        if not role:
            errors.append("نقش را انتخاب کنید")
        if CustomUser.objects.filter(username=username).exists():
            errors.append(f"نام کاربری «{username}» قبلاً استفاده شده")

        if errors:
            return render(request, self.template_name, {"errors": errors, "post": request.POST})

        user = CustomUser.objects.create_user(
            username=username, password=password,
            first_name=first, last_name=last,
            is_active=True,
        )

        if role == "technical_director":
            user.is_technical_director = True
        elif role == "finance_manager":
            user.is_finance_manager = True
        elif role == "coach":
            user.is_coach = True
        elif role == "superuser":
            user.is_superuser = True
            user.is_staff     = True

        user.save()

        # اگر مربی بود، Coach record هم بساز
        if role == "coach" and first and last:
            Coach.objects.create(
                user=user,
                first_name=first,
                last_name=last,
                phone=phone or "09000000000",
                degree=coach_degree or Coach.Degree.OTHER,
            )

        messages.success(request, f"کاربر «{username}» با موفقیت ایجاد شد.")
        logger.info("User %s created by superuser %s (role=%s)", username, request.user, role)
        return redirect("admin_panel:user-list")


# ══════════════════════════════════════════════════════════════════
#  3. ویرایش کاربر — نقش‌ها + ریست رمز
# ══════════════════════════════════════════════════════════════════

class UserEditView(SuperuserRequiredMixin, LoginRequiredMixin, View):
    template_name = "admin_panel/user_edit.html"

    def get(self, request, pk):
        user = get_object_or_404(CustomUser, pk=pk)
        # اگر بازیکن لینک داره
        player = None
        try:
            player = user.player_profile
        except Exception:
            pass
        coach = None
        try:
            coach = user.coach_profile
        except Exception:
            pass
        return render(request, self.template_name, {"u": user, "player": player, "coach": coach})

    @transaction.atomic
    def post(self, request, pk):
        user = get_object_or_404(CustomUser, pk=pk)
        action = request.POST.get("action", "")

        if action == "roles":
            user.is_technical_director = "is_technical_director" in request.POST
            user.is_finance_manager    = "is_finance_manager"    in request.POST
            user.is_coach              = "is_coach"              in request.POST
            user.is_player             = "is_player"             in request.POST
            user.is_active             = "is_active"             in request.POST
            user.save()
            messages.success(request, f"نقش‌های کاربر «{user.username}» ذخیره شد.")

        elif action == "reset_password":
            new_pw = request.POST.get("new_password", "").strip()
            if len(new_pw) < 6:
                messages.error(request, "رمز جدید باید حداقل ۶ کاراکتر باشد")
            else:
                user.set_password(new_pw)
                user.save()
                messages.success(request, f"رمز عبور «{user.username}» تغییر کرد.")

        elif action == "toggle_active":
            user.is_active = not user.is_active
            user.save()
            state = "فعال" if user.is_active else "غیرفعال"
            messages.success(request, f"حساب «{user.username}» {state} شد.")

        return redirect("admin_panel:user-edit", pk=pk)


# ══════════════════════════════════════════════════════════════════
#  4. Provision حساب بازیکنان به‌صورت دسته‌جمعی
# ══════════════════════════════════════════════════════════════════

class ProvisionPlayerAccountsView(SuperuserRequiredMixin, LoginRequiredMixin, View):
    """
    GET  → نمایش صفحه پیش‌نمایش (چند بازیکن بدون حساب دارند)
    POST → ایجاد حساب برای همه / فقط انتخاب‌شده‌ها
    """
    template_name = "admin_panel/provision_players.html"

    def get(self, request):
        players_no_account = Player.objects.filter(
            status="approved", is_archived=False, user__isnull=True
        ).order_by("last_name", "first_name")

        # پیش‌نمایش username که خواهند گرفت
        preview = []
        for p in players_no_account:
            uid = p.national_id if not p.national_id.startswith("TEMP-") else p.phone
            preview.append({
                "player": p,
                "username": uid,
                "password": uid,
            })

        return render(request, self.template_name, {
            "preview": preview,
            "count": len(preview),
        })

    @transaction.atomic
    def post(self, request):
        mode         = request.POST.get("mode", "all")   # all | selected
        selected_ids = request.POST.getlist("player_ids")

        qs = Player.objects.filter(
            status="approved", is_archived=False, user__isnull=True
        ).select_related()

        if mode == "selected" and selected_ids:
            qs = qs.filter(pk__in=[int(i) for i in selected_ids])

        created_rows = []
        errors       = []

        for player in qs:
            try:
                raw_username = (
                    player.national_id
                    if not player.national_id.startswith("TEMP-")
                    else player.phone
                )
                username = _unique_username(raw_username)
                password = raw_username  # کد ملی / موبایل

                user = CustomUser.objects.create_user(
                    username=username,
                    password=password,
                    first_name=player.first_name,
                    last_name=player.last_name,
                    is_active=True,
                    is_player=True,
                )
                player.user = user
                player.save(update_fields=["user"])

                created_rows.append({
                    "name":     f"{player.first_name} {player.last_name}",
                    "username": username,
                    "password": password,
                })
            except Exception as e:
                errors.append(f"{player}: {e}")
                logger.error("Provision error for player %s: %s", player, e)

        if "download_csv" in request.POST:
            return _credentials_csv(created_rows)

        request.session["provision_result"] = {
            "created": created_rows,
            "errors":  errors,
        }
        messages.success(request, f"✅ {len(created_rows)} حساب کاربری ایجاد شد.")
        if errors:
            messages.warning(request, f"⚠️ {len(errors)} خطا رخ داد.")
        return redirect("admin_panel:provision-result")


class ProvisionResultView(SuperuserRequiredMixin, LoginRequiredMixin, TemplateView):
    template_name = "admin_panel/provision_result.html"

    def get_context_data(self, **kwargs):
        ctx    = super().get_context_data(**kwargs)
        result = self.request.session.pop("provision_result", {"created": [], "errors": []})
        ctx["created"] = result["created"]
        ctx["errors"]  = result["errors"]
        return ctx

    def post(self, request):
        """دانلود CSV از session result"""
        result = request.session.get("provision_result", {"created": []})
        return _credentials_csv(result["created"])


def _credentials_csv(rows: list) -> HttpResponse:
    """ساخت فایل CSV اعتبارنامه‌ها"""
    output   = StringIO()
    writer   = csv.writer(output)
    writer.writerow(["نام", "نام کاربری", "رمز عبور"])
    for r in rows:
        writer.writerow([r["name"], r["username"], r["password"]])
    response = HttpResponse(output.getvalue(), content_type="text/csv; charset=utf-8-sig")
    response["Content-Disposition"] = 'attachment; filename="player_credentials.csv"'
    return response


class DownloadCredentialsView(SuperuserRequiredMixin, LoginRequiredMixin, View):
    """دانلود مستقیم CSV اعتبارنامه همه بازیکنانی که user دارن"""
    def get(self, request):
        players_with_user = Player.objects.filter(
            status="approved", is_archived=False, user__isnull=False
        ).select_related("user").order_by("last_name")

        rows = []
        for p in players_with_user:
            rows.append({
                "name": f"{p.first_name} {p.last_name}",
                "username": p.user.username,
                "password": "(رمز قبلاً ست شده — قابل نمایش نیست)",
            })
        return _credentials_csv(rows)
