"""
futsal_club/views/user_management_views.py
══════════════════════════════════════════════════════
پنل مدیریت کاربران — فقط superuser
امکانات:
  • لیست + جستجوی همه کاربران
  • ایجاد مربی / مدیر فنی / مدیر مالی
  • ویرایش کامل: نام، نام‌کاربری، موبایل، ایمیل، نقش‌ها،
                  اطلاعات مربی (درجه، شماره‌کارت، موبایل)، رمز عبور
  • Provision دسته‌جمعی حساب بازیکنان (username = کد ملی)
  • دانلود CSV اعتبارنامه‌ها
"""
from __future__ import annotations

import csv
import logging
from io import StringIO

from django.contrib import messages
from django.contrib.auth.mixins import LoginRequiredMixin
from django.core.exceptions import PermissionDenied
from django.core.paginator import Paginator
from django.db import transaction
from django.db.models import Q
from django.http import HttpResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.views import View
from django.views.generic import TemplateView

from ..models import Coach, CustomUser, Player

logger = logging.getLogger(__name__)


# ── Mixin ─────────────────────────────────────────────────────────────────────
class SuperuserRequiredMixin:
    def dispatch(self, request, *args, **kwargs):
        if not request.user.is_authenticated or not request.user.is_superuser:
            raise PermissionDenied
        return super().dispatch(request, *args, **kwargs)


# ── Helpers ───────────────────────────────────────────────────────────────────
def _unique_username(base: str) -> str:
    username, counter = base, 1
    while CustomUser.objects.filter(username=username).exists():
        username = f"{base}_{counter}"
        counter += 1
    return username


def _credentials_csv(rows: list) -> HttpResponse:
    output = StringIO()
    writer = csv.writer(output)
    writer.writerow(["نام", "نام کاربری", "رمز عبور"])
    for r in rows:
        writer.writerow([r["name"], r["username"], r["password"]])
    resp = HttpResponse(output.getvalue(), content_type="text/csv; charset=utf-8-sig")
    resp["Content-Disposition"] = 'attachment; filename="player_credentials.csv"'
    return resp


# ══════════════════════════════════════════════════════════════════
#  1. لیست کاربران
# ══════════════════════════════════════════════════════════════════
class UserListView(SuperuserRequiredMixin, LoginRequiredMixin, TemplateView):
    template_name = "admin_panel/user_list.html"

    def get(self, request, *args, **kwargs):
        q    = request.GET.get("q", "").strip()
        role = request.GET.get("role", "")
        qs   = CustomUser.objects.all().order_by("last_name", "first_name", "username")

        if q:
            qs = qs.filter(
                Q(username__icontains=q) | Q(first_name__icontains=q) |
                Q(last_name__icontains=q) | Q(phone__icontains=q)
            )
        if role == "player":          qs = qs.filter(is_player=True)
        elif role == "coach":         qs = qs.filter(is_coach=True)
        elif role == "td":            qs = qs.filter(is_technical_director=True)
        elif role == "finance":       qs = qs.filter(is_finance_manager=True)
        elif role == "superuser":     qs = qs.filter(is_superuser=True)
        elif role == "no_player_link":
            linked = Player.objects.exclude(user=None).values_list("user_id", flat=True)
            qs = qs.filter(is_player=True).exclude(pk__in=linked)

        paginator = Paginator(qs, 40)
        page_obj  = paginator.get_page(request.GET.get("page", 1))

        stats = {
            "total":      CustomUser.objects.count(),
            "players":    CustomUser.objects.filter(is_player=True).count(),
            "coaches":    CustomUser.objects.filter(is_coach=True).count(),
            "staff":      CustomUser.objects.filter(
                            Q(is_technical_director=True) | Q(is_finance_manager=True)).count(),
            "inactive":   CustomUser.objects.filter(is_active=False).count(),
            "no_account": Player.objects.filter(
                            status="approved", is_archived=False, user__isnull=True).count(),
        }
        return render(request, self.template_name,
                      {"page_obj": page_obj, "q": q, "role": role, "stats": stats})


# ══════════════════════════════════════════════════════════════════
#  2. ایجاد کاربر staff جدید
# ══════════════════════════════════════════════════════════════════
class UserCreateView(SuperuserRequiredMixin, LoginRequiredMixin, View):
    template_name = "admin_panel/user_create.html"

    def get(self, request):
        return render(request, self.template_name, {"degree_choices": Coach.Degree.choices})

    @transaction.atomic
    def post(self, request):
        username  = request.POST.get("username",   "").strip()
        password  = request.POST.get("password",   "").strip()
        first     = request.POST.get("first_name", "").strip()
        last      = request.POST.get("last_name",  "").strip()
        role      = request.POST.get("role",       "")
        phone     = request.POST.get("phone",      "").strip()
        email     = request.POST.get("email",      "").strip()
        degree    = request.POST.get("degree",     "")

        errors = []
        if not username:                               errors.append("نام کاربری الزامی است.")
        if not password or len(password) < 6:          errors.append("رمز باید حداقل ۶ کاراکتر باشد.")
        if not first:                                  errors.append("نام الزامی است.")
        if not last:                                   errors.append("نام خانوادگی الزامی است.")
        if not role:                                   errors.append("نقش را انتخاب کنید.")
        if username and CustomUser.objects.filter(username=username).exists():
            errors.append(f"نام کاربری «{username}» قبلاً استفاده شده.")

        if errors:
            return render(request, self.template_name,
                          {"errors": errors, "post": request.POST,
                           "degree_choices": Coach.Degree.choices})

        user = CustomUser.objects.create_user(
            username=username, password=password,
            first_name=first, last_name=last,
            email=email, phone=phone, is_active=True,
        )
        if role == "technical_director": user.is_technical_director = True
        elif role == "finance_manager":  user.is_finance_manager    = True
        elif role == "coach":            user.is_coach              = True
        elif role == "superuser":        user.is_superuser = True; user.is_staff = True
        user.save()

        if role == "coach":
            Coach.objects.create(
                user=user, first_name=first, last_name=last,
                phone=phone or "09000000000", degree=degree or "",
            )

        messages.success(request, f"کاربر «{username}» ایجاد شد.")
        return redirect("admin_panel:user-edit", pk=user.pk)


# ══════════════════════════════════════════════════════════════════
#  3. ویرایش کامل کاربر
# ══════════════════════════════════════════════════════════════════
class UserEditView(SuperuserRequiredMixin, LoginRequiredMixin, View):
    """
    action های POST:
      basic_info     — نام، نام‌کاربری، موبایل، ایمیل
      roles          — نقش‌ها + is_active  (اگر مربی اضافه شد، Coach record می‌سازد)
      coach_info     — نام مربی، موبایل، درجه، شماره کارت، فعال/غیرفعال
      reset_password — تغییر رمز با تأیید
      toggle_active  — تغییر سریع وضعیت فعال بودن
    """
    template_name = "admin_panel/user_edit.html"

    def _coach(self, user):
        try:   return user.coach_profile
        except: return None

    def _player(self, user):
        try:   return user.player_profile
        except: return None

    def _render(self, request, user):
        return render(request, self.template_name, {
            "u":              user,
            "coach":          self._coach(user),
            "player":         self._player(user),
            "degree_choices": Coach.Degree.choices,
        })

    def get(self, request, pk):
        return self._render(request, get_object_or_404(CustomUser, pk=pk))

    @transaction.atomic
    def post(self, request, pk):
        user   = get_object_or_404(CustomUser, pk=pk)
        action = request.POST.get("action", "")

        # ── اطلاعات پایه کاربر ───────────────────────────────────────────────
        if action == "basic_info":
            first    = request.POST.get("first_name", "").strip()
            last     = request.POST.get("last_name",  "").strip()
            username = request.POST.get("username",   "").strip()
            phone    = request.POST.get("phone",      "").strip()
            email    = request.POST.get("email",      "").strip()

            errors = []
            if not first:    errors.append("نام الزامی است.")
            if not last:     errors.append("نام خانوادگی الزامی است.")
            if not username: errors.append("نام کاربری الزامی است.")
            if username and username != user.username and \
               CustomUser.objects.filter(username=username).exists():
                errors.append(f"نام کاربری «{username}» قبلاً استفاده شده.")

            if errors:
                for e in errors: messages.error(request, e)
                return redirect("admin_panel:user-edit", pk=pk)

            user.first_name = first
            user.last_name  = last
            user.username   = username
            user.phone      = phone
            user.email      = email
            user.save(update_fields=["first_name", "last_name", "username", "phone", "email"])

            # نام مربی را هم همگام کن
            coach = self._coach(user)
            if coach:
                coach.first_name = first
                coach.last_name  = last
                coach.save(update_fields=["first_name", "last_name"])

            messages.success(request, f"اطلاعات پایه «{user.username}» ذخیره شد.")

        # ── نقش‌ها ────────────────────────────────────────────────────────────
        elif action == "roles":
            was_coach    = user.is_coach
            new_is_coach = "is_coach" in request.POST

            user.is_technical_director = "is_technical_director" in request.POST
            user.is_finance_manager    = "is_finance_manager"    in request.POST
            user.is_coach              = new_is_coach
            user.is_player             = "is_player"             in request.POST
            user.is_active             = "is_active"             in request.POST
            user.save()

            # اگر مربی تازه شد و Coach record نداشت، بساز
            if new_is_coach and not was_coach and not self._coach(user):
                Coach.objects.create(
                    user=user, first_name=user.first_name, last_name=user.last_name,
                    phone=user.phone or "09000000000",
                )
                messages.info(request, "پروفایل مربی ایجاد شد — اطلاعات تکمیلی را وارد کنید.")

            messages.success(request, f"نقش‌های «{user.username}» ذخیره شد.")

        # ── اطلاعات مربی ─────────────────────────────────────────────────────
        elif action == "coach_info":
            coach = self._coach(user)
            if not coach:
                messages.error(request, "این کاربر پروفایل مربی ندارد.")
                return redirect("admin_panel:user-edit", pk=pk)

            c_first  = request.POST.get("coach_first_name", "").strip()
            c_last   = request.POST.get("coach_last_name",  "").strip()
            c_phone  = request.POST.get("coach_phone",      "").strip()
            degree   = request.POST.get("degree",           "").strip()
            card     = (request.POST.get("bank_card_number", "")
                        .strip().replace("-", "").replace(" ", ""))
            c_active = "coach_is_active" in request.POST

            errors = []
            if card and not card.isdigit():      errors.append("شماره کارت باید فقط عدد باشد.")
            if card and len(card) not in (0, 16): errors.append("شماره کارت باید ۱۶ رقم باشد.")
            if errors:
                for e in errors: messages.error(request, e)
                return redirect("admin_panel:user-edit", pk=pk)

            if c_first:  coach.first_name = c_first
            if c_last:   coach.last_name  = c_last
            if c_phone:  coach.phone      = c_phone
            if degree:   coach.degree     = degree
            coach.bank_card_number = card
            coach.is_active        = c_active
            coach.save(update_fields=[
                "first_name", "last_name", "phone", "degree", "bank_card_number", "is_active"
            ])
            messages.success(request, f"اطلاعات مربی «{coach}» ذخیره شد.")

        # ── تغییر رمز عبور ───────────────────────────────────────────────────
        elif action == "reset_password":
            new_pw  = request.POST.get("new_password",     "").strip()
            conf_pw = request.POST.get("confirm_password", "").strip()
            if len(new_pw) < 6:
                messages.error(request, "رمز جدید باید حداقل ۶ کاراکتر باشد.")
            elif new_pw != conf_pw:
                messages.error(request, "رمز عبور و تکرار آن یکسان نیستند.")
            else:
                user.set_password(new_pw)
                user.save()
                messages.success(request, f"رمز عبور «{user.username}» تغییر کرد.")

        # ── فعال/غیرفعال سریع ────────────────────────────────────────────────
        elif action == "toggle_active":
            user.is_active = not user.is_active
            user.save(update_fields=["is_active"])
            state = "فعال" if user.is_active else "غیرفعال"
            messages.success(request, f"حساب «{user.username}» {state} شد.")

        return redirect("admin_panel:user-edit", pk=pk)


# ══════════════════════════════════════════════════════════════════
#  4. Provision حساب بازیکنان دسته‌جمعی
# ══════════════════════════════════════════════════════════════════
class ProvisionPlayerAccountsView(SuperuserRequiredMixin, LoginRequiredMixin, View):
    template_name = "admin_panel/provision_players.html"

    def get(self, request):
        no_acc = Player.objects.filter(
            status="approved", is_archived=False, user__isnull=True
        ).order_by("last_name", "first_name")
        preview = []
        for p in no_acc:
            uid = p.national_id if not p.national_id.startswith("TEMP-") else p.phone
            preview.append({"player": p, "username": uid, "password": uid})
        return render(request, self.template_name, {"preview": preview, "count": len(preview)})

    @transaction.atomic
    def post(self, request):
        mode     = request.POST.get("mode", "all")
        sel_ids  = request.POST.getlist("player_ids")
        qs = Player.objects.filter(status="approved", is_archived=False, user__isnull=True)
        if mode == "selected" and sel_ids:
            qs = qs.filter(pk__in=[int(i) for i in sel_ids])

        created, errors = [], []
        for player in qs:
            try:
                raw   = player.national_id if not player.national_id.startswith("TEMP-") else player.phone
                uname = _unique_username(raw)
                u     = CustomUser.objects.create_user(
                    username=uname, password=raw,
                    first_name=player.first_name, last_name=player.last_name,
                    is_active=True, is_player=True,
                )
                player.user = u
                player.save(update_fields=["user"])
                created.append({"name": f"{player.first_name} {player.last_name}",
                                "username": uname, "password": raw})
            except Exception as e:
                errors.append(f"{player}: {e}")

        if "download_csv" in request.POST:
            return _credentials_csv(created)

        request.session["provision_result"] = {"created": created, "errors": errors}
        messages.success(request, f"✅ {len(created)} حساب کاربری ایجاد شد.")
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
        result = request.session.get("provision_result", {"created": []})
        return _credentials_csv(result["created"])


class DownloadCredentialsView(SuperuserRequiredMixin, LoginRequiredMixin, View):
    def get(self, request):
        players = Player.objects.filter(
            status="approved", is_archived=False, user__isnull=False
        ).select_related("user").order_by("last_name")
        rows = [{"name": f"{p.first_name} {p.last_name}",
                 "username": p.user.username, "password": "(قبلاً ست شده)"} for p in players]
        return _credentials_csv(rows)