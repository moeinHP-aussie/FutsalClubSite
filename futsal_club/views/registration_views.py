"""
views/registration_views.py
─────────────────────────────────────────────────────────────────────
ثبت‌نام بازیکن جدید + گردش‌کار تأیید مدیر فنی
Registration Workflow: New Applicant → Pending → TechnicalDirector Review → Approved/Player
"""
from __future__ import annotations

import logging
from typing import Any

from django.contrib import messages
from django.contrib.auth.mixins import LoginRequiredMixin
from django.db import transaction
from django.http import JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse_lazy
from django.utils import timezone
from django.views import View
from django.views.generic import DetailView, FormView, ListView, TemplateView

from ..forms.registration_forms import ApplicantRegistrationForm, TechnicalProfileForm
from ..mixins import RoleRequiredMixin
from ..models import CustomUser, Notification, Player, TrainingCategory

logger = logging.getLogger(__name__)


# ────────────────────────────────────────────────────────────────────
#  1. Public Registration Form (New Applicant)
# ────────────────────────────────────────────────────────────────────

class ApplicantRegistrationView(FormView):
    """
    صفحه ثبت‌نام عمومی — نیازی به لاگین ندارد.
    پس از ثبت، وضعیت Pending می‌شود و منتظر تأیید مدیر فنی می‌ماند.
    """
    template_name = "registration/applicant_form.html"
    form_class    = ApplicantRegistrationForm
    success_url   = reverse_lazy("registration:success")

    @transaction.atomic
    def form_valid(self, form):
        data = form.cleaned_data

        # ── ایجاد CustomUser برای متقاضی ─────────────────────────
        username = self._generate_username(data["national_id"])
        user = CustomUser.objects.create_user(
            username         = username,
            password         = data["national_id"],   # رمز اولیه = کد ملی
            first_name       = data["first_name"],
            last_name        = data["last_name"],
            phone            = data["phone"],
            is_new_applicant = True,
        )

        # ── ایجاد Player با وضعیت Pending ───────────────────────
        player = Player(
            user             = user,
            first_name       = data["first_name"],
            last_name        = data["last_name"],
            father_name      = data["father_name"],
            national_id      = data["national_id"],
            dob              = data["dob"],
            phone            = data["phone"],
            father_phone     = data["father_phone"],
            mother_phone     = data.get("mother_phone", ""),
            address          = data.get("address", ""),
            height           = data.get("height"),
            weight           = data.get("weight"),
            preferred_hand   = data.get("preferred_hand", "R"),
            preferred_foot   = data.get("preferred_foot", "R"),
            medical_history  = data.get("medical_history", ""),
            injury_history   = data.get("injury_history", ""),
            father_education = data.get("father_education", ""),
            father_job       = data.get("father_job", ""),
            mother_education = data.get("mother_education", ""),
            mother_job       = data.get("mother_job", ""),
            insurance_status = data.get("insurance_status", "none"),
            status           = Player.Status.PENDING,
        )
        player.save()

        # ── اعلان به مدیران فنی ──────────────────────────────────
        self._notify_technical_directors(player)

        logger.info("متقاضی جدید ثبت شد: %s (national_id=%s)", player, data["national_id"])

        # ذخیره در session برای صفحه موفقیت
        self.request.session["new_applicant_id"] = player.player_id
        return super().form_valid(form)

    def form_invalid(self, form):
        messages.error(self.request, "لطفاً خطاهای فرم را بررسی و اصلاح کنید.")
        return super().form_invalid(form)

    @staticmethod
    def _generate_username(national_id: str) -> str:
        """ساخت نام کاربری یکتا از کد ملی."""
        base = f"player_{national_id}"
        if CustomUser.objects.filter(username=base).exists():
            import random, string
            suffix = "".join(random.choices(string.digits, k=4))
            return f"{base}_{suffix}"
        return base

    @staticmethod
    def _notify_technical_directors(player: Player):
        directors = CustomUser.objects.filter(is_technical_director=True, is_active=True)
        notifs = [
            Notification(
                recipient   = td,
                type        = Notification.NotificationType.GENERAL,
                title       = "متقاضی جدید",
                message     = (
                    f"متقاضی جدیدی به نام {player.first_name} {player.last_name} "
                    f"(کد ملی: {player.national_id}) ثبت‌نام کرده است و منتظر بررسی است."
                ),
                related_player = player,
            )
            for td in directors
        ]
        Notification.objects.bulk_create(notifs)


class RegistrationSuccessView(TemplateView):
    template_name = "registration/success.html"

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx["player_id"] = self.request.session.pop("new_applicant_id", None)
        return ctx


# ────────────────────────────────────────────────────────────────────
#  2. Technical Director — Applicant Management
# ────────────────────────────────────────────────────────────────────

class ApplicantListView(LoginRequiredMixin, RoleRequiredMixin, ListView):
    """
    لیست متقاضیان در انتظار تأیید — فقط مدیر فنی.
    فیلتر: status=pending (پیش‌فرض) | all | rejected
    """
    allowed_roles       = ["is_technical_director"]
    template_name       = "registration/applicant_list.html"
    context_object_name = "applicants"
    paginate_by         = 20

    def get_queryset(self):
        status_filter = self.request.GET.get("status", "pending")
        qs = Player.objects.filter(is_archived=False).select_related("user")

        if status_filter == "pending":
            qs = qs.filter(status=Player.Status.PENDING)
        elif status_filter == "rejected":
            qs = qs.filter(status=Player.Status.REJECTED)
        elif status_filter == "approved":
            qs = qs.filter(status=Player.Status.APPROVED)
        # "all" → no status filter

        search = self.request.GET.get("q", "").strip()
        if search:
            qs = qs.filter(
                first_name__icontains=search
            ) | qs.filter(
                last_name__icontains=search
            ) | qs.filter(
                national_id__icontains=search
            )

        return qs.order_by("-registration_date")

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx["status_filter"]   = self.request.GET.get("status", "pending")
        ctx["search_query"]    = self.request.GET.get("q", "")
        ctx["pending_count"]   = Player.objects.filter(status=Player.Status.PENDING, is_archived=False).count()
        ctx["categories"]      = TrainingCategory.objects.filter(is_active=True)
        return ctx


class ApplicantDetailView(LoginRequiredMixin, RoleRequiredMixin, DetailView):
    """پروفایل کامل متقاضی برای بررسی توسط مدیر فنی."""
    allowed_roles       = ["is_technical_director"]
    template_name       = "registration/applicant_detail.html"
    context_object_name = "player"
    queryset            = Player.objects.filter(is_archived=False)

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx["categories"]      = TrainingCategory.objects.filter(is_active=True)
        ctx["tech_form"]       = TechnicalProfileForm(instance=getattr(self.object, "technical_profile", None))
        ctx["age_category"]    = self.object.get_age_category()
        return ctx


class ApproveApplicantView(LoginRequiredMixin, RoleRequiredMixin, View):
    """
    تأیید متقاضی + اختصاص به دسته آموزشی.
    POST  /registration/applicants/<pk>/approve/
    body: { category_ids: [1,2], shirt_number: 7, position: "pivot", skill_level: "B" }
    """
    allowed_roles     = ["is_technical_director"]
    http_method_names = ["post"]

    @transaction.atomic
    def post(self, request, pk: int):
        player = get_object_or_404(Player, pk=pk, is_archived=False)

        if player.status == Player.Status.APPROVED:
            messages.warning(request, "این بازیکن قبلاً تأیید شده است.")
            return redirect("registration:applicant-list")

        # ── تأیید بازیکن ─────────────────────────────────────────
        player.status        = Player.Status.APPROVED
        player.approved_by   = request.user
        player.approval_date = timezone.now()
        player.save(update_fields=["status", "approved_by", "approval_date"])

        # ── به‌روزرسانی نقش کاربری ────────────────────────────────
        if player.user:
            player.user.is_player        = True
            player.user.is_new_applicant = False
            player.user.save(update_fields=["is_player", "is_new_applicant"])

        # ── اختصاص به دسته‌های آموزشی ───────────────────────────
        category_ids = request.POST.getlist("category_ids")
        if category_ids:
            cats = TrainingCategory.objects.filter(pk__in=category_ids, is_active=True)
            player.categories.set(cats)

        # ── ایجاد پروفایل فنی ────────────────────────────────────
        from ..models import TechnicalProfile
        tp, _ = TechnicalProfile.objects.get_or_create(player=player)
        shirt      = request.POST.get("shirt_number")
        position   = request.POST.get("position", "-")
        skill      = request.POST.get("skill_level", "")
        two_footed = request.POST.get("is_two_footed") == "on"

        if shirt:
            try:
                tp.shirt_number = int(shirt)
            except ValueError:
                pass
        tp.position      = position
        tp.skill_level   = skill
        tp.is_two_footed = two_footed
        tp.updated_by    = request.user
        tp.save()

        # ── اعلان به بازیکن ───────────────────────────────────────
        if player.user:
            Notification.objects.create(
                recipient      = player.user,
                type           = Notification.NotificationType.GENERAL,
                title          = "✅ ثبت‌نام شما تأیید شد",
                message        = (
                    f"ثبت‌نام شما در باشگاه فوتسال با موفقیت تأیید شد. "
                    f"اکنون می‌توانید وارد سیستم شوید.\n"
                    f"نام کاربری: {player.user.username}\n"
                    f"رمز اولیه: {player.national_id} (لطفاً تغییر دهید)"
                ),
                related_player = player,
            )

        messages.success(request, f"بازیکن {player} با موفقیت تأیید شد.")
        logger.info("بازیکن تأیید شد: %s توسط %s", player, request.user)
        return redirect("registration:applicant-list")


class RejectApplicantView(LoginRequiredMixin, RoleRequiredMixin, View):
    """رد کردن متقاضی با ذکر دلیل."""
    allowed_roles     = ["is_technical_director"]
    http_method_names = ["post"]

    def post(self, request, pk: int):
        player = get_object_or_404(Player, pk=pk, is_archived=False)
        reason = request.POST.get("rejection_reason", "").strip()

        player.status = Player.Status.REJECTED
        player.notes  = f"دلیل رد: {reason}" if reason else player.notes
        player.save(update_fields=["status", "notes"])

        if player.user:
            Notification.objects.create(
                recipient      = player.user,
                type           = Notification.NotificationType.GENERAL,
                title          = "❌ ثبت‌نام رد شد",
                message        = f"متأسفانه ثبت‌نام شما رد شد.{' دلیل: ' + reason if reason else ''}",
                related_player = player,
            )

        messages.warning(request, f"ثبت‌نام {player} رد شد.")
        return redirect("registration:applicant-list")


# ────────────────────────────────────────────────────────────────────
#  3. Archive (Soft Delete) Views
# ────────────────────────────────────────────────────────────────────

class ArchivePlayerView(LoginRequiredMixin, RoleRequiredMixin, View):
    """آرشیو نرم بازیکن — بدون حذف از دیتابیس."""
    allowed_roles     = ["is_technical_director"]
    http_method_names = ["post"]

    def post(self, request, pk: int):
        player = get_object_or_404(Player, pk=pk, is_archived=False)
        reason = request.POST.get("archive_reason", "").strip()

        player.archive(reason=reason)

        # غیرفعال کردن حساب کاربری
        if player.user:
            player.user.is_active  = False
            player.user.is_player  = False
            player.user.save(update_fields=["is_active", "is_player"])

        messages.success(request, f"بازیکن {player} آرشیو شد.")
        return redirect(request.POST.get("next", "registration:player-list"))


class ArchivedPlayerListView(LoginRequiredMixin, RoleRequiredMixin, ListView):
    """لیست بازیکنان آرشیو‌شده."""
    allowed_roles       = ["is_technical_director"]
    template_name       = "registration/archived_players.html"
    context_object_name = "players"
    paginate_by         = 20

    def get_queryset(self):
        qs = Player.objects.filter(is_archived=True).select_related("user", "approved_by")
        q  = self.request.GET.get("q", "").strip()
        if q:
            qs = qs.filter(first_name__icontains=q) | qs.filter(
                last_name__icontains=q) | qs.filter(national_id__icontains=q)
        return qs.order_by("-archived_at")

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx["total_archived"] = Player.objects.filter(is_archived=True).count()
        ctx["search_query"]   = self.request.GET.get("q", "")
        return ctx


class RestorePlayerView(LoginRequiredMixin, RoleRequiredMixin, View):
    """بازگردانی بازیکن آرشیو‌شده به وضعیت فعال."""
    allowed_roles     = ["is_technical_director"]
    http_method_names = ["post"]

    @transaction.atomic
    def post(self, request, pk: int):
        player = get_object_or_404(Player, pk=pk, is_archived=True)

        player.is_archived    = False
        player.status         = Player.Status.APPROVED
        player.archived_at    = None
        player.archive_reason = ""
        player.save(update_fields=["is_archived", "status", "archived_at", "archive_reason"])

        if player.user:
            player.user.is_active = True
            player.user.is_player = True
            player.user.save(update_fields=["is_active", "is_player"])

            Notification.objects.create(
                recipient      = player.user,
                type           = Notification.NotificationType.GENERAL,
                title          = "✅ حساب شما بازگردانی شد",
                message        = "حساب کاربری شما توسط مدیر فنی بازگردانی شد. خوش آمدید!",
                related_player = player,
            )

        messages.success(request, f"بازیکن {player} با موفقیت بازگردانی شد.")
        return redirect("registration:archived-players")
