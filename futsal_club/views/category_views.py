"""
futsal_club/views/category_views.py
─────────────────────────────────────────────────────────────────────
Views برای مدیریت دسته‌های آموزشی، مربیان، حضور و غیاب و پروفایل بازیکن.

شامل:
  - CategoryListView / CategoryCreateView / CategoryUpdateView / CategoryDetailView
  - CoachListView / CoachCreateView / CoachUpdateView / CoachDetailView
  - AttendanceCategorySelectView
  - PlayerProfileView / PlayerInvoiceListView
"""

from django import forms
from django.contrib import messages
from django.contrib.auth.mixins import LoginRequiredMixin
from django.core.exceptions import PermissionDenied
from django.db.models import Count, Q, Sum
from django.shortcuts import get_object_or_404, redirect
from django.urls import reverse_lazy
from django.views.generic import (
    CreateView, DeleteView, DetailView, ListView, TemplateView, UpdateView, View,
)
from django.utils.translation import gettext_lazy as _

from ..mixins import RoleRequiredMixin
from ..models import PlayerChangeLog
from ..models import (
    Coach, CoachCategoryRate, CustomUser,
    Player, TrainingCategory, TrainingSchedule,
)

# ══════════════════════════════════════════════════════════════════
#  مدیریت دسته‌های آموزشی
# ══════════════════════════════════════════════════════════════════

class CategoryListView(LoginRequiredMixin, RoleRequiredMixin, ListView):
    """لیست تمام دسته‌های آموزشی"""
    model = TrainingCategory
    template_name = "training/category_list.html"
    context_object_name = "categories"
    allowed_roles = ["is_technical_director", "is_coach", "is_finance_manager"]

    def get_queryset(self):
        qs = TrainingCategory.objects.prefetch_related(
            "coaches", "players", "schedules"
        ).annotate(
            player_count=Count("players", distinct=True),
            coach_count=Count("coaches", distinct=True),
        )
        # مربی فقط دسته‌های خودش رو می‌بینه
        if self.request.user.is_coach and not self.request.user.is_superuser:
            try:
                coach = self.request.user.coach_profile
                qs = qs.filter(coaches=coach)
            except Coach.DoesNotExist:
                qs = qs.none()
        q = self.request.GET.get("q", "").strip()
        if q:
            qs = qs.filter(name__icontains=q)
        show = self.request.GET.get("show", "active")
        if show == "inactive":
            qs = qs.filter(is_active=False)
        elif show == "active":
            qs = qs.filter(is_active=True)
        return qs.order_by("name")

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx["q"]    = self.request.GET.get("q", "")
        ctx["show"] = self.request.GET.get("show", "active")
        ctx["total_active"]   = TrainingCategory.objects.filter(is_active=True).count()
        ctx["total_inactive"] = TrainingCategory.objects.filter(is_active=False).count()
        return ctx


class CategoryForm(forms.ModelForm):
    """فرم ایجاد / ویرایش دسته آموزشی"""
    class Meta:
        model  = TrainingCategory
        fields = ["name", "description", "monthly_fee", "is_active"]
        widgets = {
            "name":        forms.TextInput(attrs={"placeholder": "مثال: نونهالان الف"}),
            "description": forms.Textarea(attrs={"rows": 3, "placeholder": "توضیحات اختیاری"}),
            "monthly_fee": forms.NumberInput(attrs={"placeholder": "شهریه ماهانه به ریال"}),
        }
        labels = {
            "name":        "نام دسته",
            "description": "توضیحات",
            "monthly_fee": "شهریه ماهانه (ریال)",
            "is_active":   "فعال",
        }


class CategoryCreateView(LoginRequiredMixin, RoleRequiredMixin, CreateView):
    model         = TrainingCategory
    form_class    = CategoryForm
    template_name = "training/category_form.html"
    allowed_roles = ["is_technical_director"]
    success_url   = reverse_lazy("training:category-list")

    def form_valid(self, form):
        messages.success(self.request, f"دسته «{form.instance.name}» با موفقیت ایجاد شد.")
        return super().form_valid(form)

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx["is_edit"] = False
        return ctx


class CategoryUpdateView(LoginRequiredMixin, RoleRequiredMixin, UpdateView):
    model         = TrainingCategory
    form_class    = CategoryForm
    template_name = "training/category_form.html"
    allowed_roles = ["is_technical_director"]
    success_url   = reverse_lazy("training:category-list")

    def form_valid(self, form):
        messages.success(self.request, f"دسته «{form.instance.name}» بروزرسانی شد.")
        return super().form_valid(form)

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx["is_edit"] = True
        return ctx


class CategoryDetailView(LoginRequiredMixin, RoleRequiredMixin, DetailView):
    """جزئیات دسته: بازیکنان، مربیان، برنامه تمرین"""
    model         = TrainingCategory
    template_name = "training/category_detail.html"
    context_object_name = "category"
    allowed_roles = ["is_technical_director", "is_coach", "is_finance_manager"]

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        cat = self.object
        ctx["players"]   = cat.players.filter(status="approved").order_by("last_name")
        ctx["schedules"] = cat.schedules.all().order_by("weekday", "start_time")
        ctx["coach_rates"] = CoachCategoryRate.objects.filter(
            category=cat, is_active=True
        ).select_related("coach")
        return ctx


class CategoryToggleActiveView(LoginRequiredMixin, RoleRequiredMixin, View):
    """فعال/غیرفعال کردن دسته"""
    allowed_roles = ["is_technical_director"]

    def post(self, request, pk):
        cat = get_object_or_404(TrainingCategory, pk=pk)
        cat.is_active = not cat.is_active
        cat.save()
        state = "فعال" if cat.is_active else "غیرفعال"
        messages.success(request, f"دسته «{cat.name}» {state} شد.")
        return redirect("training:category-list")


class CategoryDeleteView(LoginRequiredMixin, RoleRequiredMixin, DeleteView):
    """حذف دسته آموزشی — فقط مدیر فنی."""
    allowed_roles = ["is_technical_director"]
    model         = TrainingCategory
    template_name = "training/category_confirm_delete.html"
    success_url   = reverse_lazy("training:category-list")

    def form_valid(self, form):
        obj = self.get_object()
        name = obj.name
        # جدا کردن بازیکنان قبل از حذف
        obj.players.clear()
        obj.coaches.clear()
        messages.success(self.request, f"دسته «{name}» حذف شد.")
        return super().form_valid(form)


# ══════════════════════════════════════════════════════════════════
#  مدیریت مربیان
# ══════════════════════════════════════════════════════════════════

class CoachListView(LoginRequiredMixin, RoleRequiredMixin, ListView):
    """لیست تمام مربیان"""
    model = Coach
    template_name = "training/coach_list.html"
    context_object_name = "coaches"
    allowed_roles = ["is_technical_director", "is_finance_manager"]

    def get_queryset(self):
        qs = Coach.objects.select_related("user").prefetch_related(
            "categories"
        ).annotate(
            category_count=Count("categories", distinct=True)
        )
        q = self.request.GET.get("q", "").strip()
        if q:
            qs = qs.filter(
                Q(first_name__icontains=q) |
                Q(last_name__icontains=q)  |
                Q(phone__icontains=q)
            )
        show = self.request.GET.get("show", "active")
        if show == "inactive":
            qs = qs.filter(is_active=False)
        elif show == "active":
            qs = qs.filter(is_active=True)
        return qs.order_by("last_name", "first_name")

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx["q"]    = self.request.GET.get("q", "")
        ctx["show"] = self.request.GET.get("show", "active")
        ctx["total_active"]   = Coach.objects.filter(is_active=True).count()
        ctx["total_inactive"] = Coach.objects.filter(is_active=False).count()
        return ctx


class CoachForm(forms.ModelForm):
    """فرم ایجاد/ویرایش مربی"""
    # انتخاب کاربر موجود برای اتصال به مربی
    user = forms.ModelChoiceField(
        queryset=CustomUser.objects.filter(is_coach=True),
        label="حساب کاربری مربی",
        required=False,
        help_text="کاربری که نقش مربی داره (اختیاری)",
    )

    class Meta:
        model  = Coach
        fields = ["user", "first_name", "last_name", "degree", "phone",
                  "bank_card_number", "is_active"]
        widgets = {
            "first_name":       forms.TextInput(attrs={"placeholder": "نام"}),
            "last_name":        forms.TextInput(attrs={"placeholder": "نام خانوادگی"}),
            "phone":            forms.TextInput(attrs={"placeholder": "09xxxxxxxxx", "inputmode": "numeric"}),
            "bank_card_number": forms.TextInput(attrs={"placeholder": "۱۶ رقم بدون فاصله", "inputmode": "numeric", "maxlength": "16"}),
        }
        labels = {
            "first_name":       "نام",
            "last_name":        "نام خانوادگی",
            "degree":           "مدرک مربیگری",
            "phone":            "موبایل",
            "bank_card_number": "شماره کارت بانکی",
            "is_active":        "فعال",
        }


class CoachCreateView(LoginRequiredMixin, RoleRequiredMixin, CreateView):
    model         = Coach
    form_class    = CoachForm
    template_name = "training/coach_form.html"
    allowed_roles = ["is_technical_director"]
    success_url   = reverse_lazy("training:coach-list")

    def form_valid(self, form):
        messages.success(self.request,
            f"مربی «{form.instance.first_name} {form.instance.last_name}» اضافه شد.")
        return super().form_valid(form)

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx["is_edit"] = False
        return ctx


class CoachUpdateView(LoginRequiredMixin, RoleRequiredMixin, UpdateView):
    model         = Coach
    form_class    = CoachForm
    template_name = "training/coach_form.html"
    allowed_roles = ["is_technical_director"]
    success_url   = reverse_lazy("training:coach-list")

    def form_valid(self, form):
        messages.success(self.request,
            f"اطلاعات مربی «{form.instance.first_name} {form.instance.last_name}» بروزرسانی شد.")
        return super().form_valid(form)

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx["is_edit"] = True
        return ctx


class CoachDetailView(LoginRequiredMixin, RoleRequiredMixin, DetailView):
    model         = Coach
    template_name = "training/coach_detail.html"
    context_object_name = "coach"
    allowed_roles = ["is_technical_director", "is_finance_manager"]

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx["coach_rates"] = CoachCategoryRate.objects.filter(
            coach=self.object
        ).select_related("category")
        return ctx


class CoachToggleActiveView(LoginRequiredMixin, RoleRequiredMixin, View):
    allowed_roles = ["is_technical_director"]

    def post(self, request, pk):
        coach = get_object_or_404(Coach, pk=pk)
        coach.is_active = not coach.is_active
        coach.save()
        state = "فعال" if coach.is_active else "غیرفعال"
        messages.success(request,
            f"مربی «{coach.first_name} {coach.last_name}» {state} شد.")
        return redirect("training:coach-list")


# ══════════════════════════════════════════════════════════════════
#  انتخاب دسته برای حضور و غیاب
# ══════════════════════════════════════════════════════════════════

class AttendanceCategorySelectView(LoginRequiredMixin, RoleRequiredMixin, TemplateView):
    """
    صفحه انتخاب دسته قبل از رفتن به ماتریس حضور.
    کاربر روی یک دسته کلیک می‌کند → redirect به attendance:matrix
    """
    template_name = "training/attendance_select.html"
    allowed_roles = ["is_technical_director", "is_coach"]

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        qs = TrainingCategory.objects.filter(is_active=True).annotate(
            player_count=Count("players", distinct=True)
        ).prefetch_related("schedules")

        if self.request.user.is_coach and not self.request.user.is_superuser:
            try:
                coach = self.request.user.coach_profile
                qs = qs.filter(coaches=coach)
            except Coach.DoesNotExist:
                qs = qs.none()

        ctx["categories"] = qs.order_by("name")
        return ctx


# ══════════════════════════════════════════════════════════════════
#  پروفایل بازیکن (دید خود بازیکن)
# ══════════════════════════════════════════════════════════════════

class PlayerProfileView(LoginRequiredMixin, TemplateView):
    """پروفایل شخصی بازیکن"""
    template_name = "training/player_profile.html"

    def dispatch(self, request, *args, **kwargs):
        if not request.user.is_authenticated:
            return self.handle_no_permission()
        # سوپریوزر و مدیر فنی می‌توانند هر بازیکنی رو ببینند
        pk = kwargs.get("pk")
        if pk:
            if not (request.user.is_superuser or
                    request.user.is_technical_director):
                raise PermissionDenied
        return super().dispatch(request, *args, **kwargs)

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        pk = self.kwargs.get("pk")
        if pk:
            player = get_object_or_404(Player, pk=pk, status="approved")
        else:
            try:
                player = self.request.user.player_profile
            except Player.DoesNotExist:
                player = None

        ctx["player"] = player
        if player:
            ctx["categories"]       = player.categories.filter(is_active=True)
            ctx["recent_invoices"]  = player.invoices.order_by("-created_at")[:5] if hasattr(player, "invoices") else []

            # پروفایل فنی
            from ..models import TechnicalProfile, SoftTraitType, PlayerSoftTrait
            tp, _ = TechnicalProfile.objects.get_or_create(player=player)
            ctx["tech_profile"] = tp

            # ویژگی‌های نرم — همه انواع فعال + امتیاز موجود
            all_trait_types = SoftTraitType.objects.filter(is_active=True).order_by("name")
            existing_traits = {t.trait_type_id: t for t in tp.soft_traits.select_related("trait_type").all()}
            ctx["soft_traits"]      = [
                {
                    "type":  tt,
                    "trait": existing_traits.get(tt.pk),
                    "score": existing_traits[tt.pk].score if tt.pk in existing_traits else 0,
                }
                for tt in all_trait_types
            ]
            ctx["soft_trait_types"] = all_trait_types
            ctx["can_edit_tech"]    = (
                self.request.user.is_technical_director or
                self.request.user.is_coach or
                self.request.user.is_superuser
            )
        return ctx


class PlayerListView(LoginRequiredMixin, RoleRequiredMixin, ListView):
    """لیست بازیکنان تأیید‌شده با قابلیت فیلتر"""
    model = Player
    template_name = "training/player_list.html"
    context_object_name = "players"
    paginate_by = 25
    allowed_roles = ["is_technical_director", "is_coach", "is_finance_manager"]

    def get_queryset(self):
        qs = Player.objects.filter(status="approved", is_archived=False).order_by("last_name", "first_name")
        q = self.request.GET.get("q", "").strip()
        if q:
            qs = qs.filter(
                Q(first_name__icontains=q) |
                Q(last_name__icontains=q)  |
                Q(national_id__icontains=q)|
                Q(phone__icontains=q)
            )
        category = self.request.GET.get("category", "")
        if category:
            qs = qs.filter(categories__pk=category)

        # فیلترهای پیشرفته
        position = self.request.GET.get("position", "")
        if position:
            qs = qs.filter(technical_profile__position=position)

        skill = self.request.GET.get("skill_level", "")
        if skill:
            qs = qs.filter(technical_profile__skill_level=skill)

        foot = self.request.GET.get("preferred_foot", "")
        if foot:
            qs = qs.filter(preferred_foot=foot)

        two_footed = self.request.GET.get("two_footed", "")
        if two_footed == "1":
            qs = qs.filter(technical_profile__is_two_footed=True)
        elif two_footed == "0":
            qs = qs.filter(technical_profile__is_two_footed=False)

        insurance = self.request.GET.get("insurance", "")
        if insurance:
            qs = qs.filter(insurance_status=insurance)

        # فیلتر رده سنی - در memory
        age_filter = self.request.GET.get("age_cat", "").strip()
        if age_filter:
            filtered_ids = [
                p.pk for p in qs.exclude(dob__isnull=True)
                if p.get_age_category() == age_filter
            ]
            qs = qs.filter(pk__in=filtered_ids)

        return qs.select_related("technical_profile").prefetch_related("categories").distinct()

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx["q"]              = self.request.GET.get("q", "")
        ctx["category_filter"]= self.request.GET.get("category", "")
        ctx["foot_filter"]    = self.request.GET.get("foot", "")
        ctx["all_categories"] = TrainingCategory.objects.filter(is_active=True).order_by("name")
        ctx["total_count"]    = Player.objects.filter(status="approved", is_archived=False).count()

        # ── آمار رده سنی برای نوار فیلتر ─────────────────────
        from collections import Counter
        all_players = Player.objects.filter(status="approved", is_archived=False).exclude(dob__isnull=True)
        age_cnt = Counter()
        for p in all_players:
            age_cnt[p.get_age_category()] += 1
        def _sort_key(t):
            c = t[0]
            if c.startswith("زیر "):
                try: return int(c.split()[1])
                except: pass
            return 100
        ctx["age_category_counts"] = sorted(age_cnt.items(), key=_sort_key)
        ctx["age_filter"]       = self.request.GET.get("age_cat", "")
        ctx["filter_position"]  = self.request.GET.get("position", "")
        ctx["filter_skill"]     = self.request.GET.get("skill_level", "")
        ctx["filter_foot"]      = self.request.GET.get("preferred_foot", "")
        ctx["filter_two_footed"]= self.request.GET.get("two_footed", "")
        ctx["filter_insurance"] = self.request.GET.get("insurance", "")
        ctx["has_adv_filter"]   = any([
            ctx["filter_position"], ctx["filter_skill"],
            ctx["filter_foot"], ctx["filter_two_footed"],
            ctx["filter_insurance"],
        ])
        return ctx


# ══════════════════════════════════════════════════════════════════
#  ویرایش پروفایل فنی بازیکن
# ══════════════════════════════════════════════════════════════════

class TechnicalProfileUpdateView(LoginRequiredMixin, RoleRequiredMixin, View):
    """
    POST /training/players/<pk>/tech/
    ویرایش inline پروفایل فنی: شماره پیراهن، پست، سطح، دوپا، یادداشت
    """
    allowed_roles     = ["is_technical_director", "is_coach"]
    http_method_names = ["post"]

    def post(self, request, pk):
        from ..models import TechnicalProfile
        import json
        player = get_object_or_404(Player, pk=pk, status="approved")
        tp, _  = TechnicalProfile.objects.get_or_create(player=player)

        tp.shirt_number  = request.POST.get("shirt_number") or None
        tp.position      = request.POST.get("position", "-")
        tp.skill_level   = request.POST.get("skill_level", "")
        tp.is_two_footed = request.POST.get("is_two_footed") == "on"
        tp.coach_notes   = request.POST.get("coach_notes", "")
        tp.updated_by    = request.user
        tp.save()

        from ..models import PlayerChangeLog
        from ..views.player_edit_views import _notify_about_player_change
        PlayerChangeLog.objects.create(
            player=player, changed_by=request.user,
            change_type=PlayerChangeLog.ChangeType.TECH,
            description="ویرایش پروفایل فنی (پست، سطح، شماره پیراهن)",
        )
        _notify_about_player_change(request.user, player, "ویرایش پروفایل فنی ⚽")

        messages.success(request, "پروفایل فنی بروز شد.")
        return redirect("training:player-profile", pk=pk)


class SoftTraitUpdateView(LoginRequiredMixin, RoleRequiredMixin, View):
    """
    POST /training/players/<pk>/soft-traits/
    ذخیره/بروزرسانی تمام ویژگی‌های نرم یک بازیکن
    """
    allowed_roles     = ["is_technical_director", "is_coach"]
    http_method_names = ["post"]

    def post(self, request, pk):
        from ..models import TechnicalProfile, SoftTraitType, PlayerSoftTrait
        player = get_object_or_404(Player, pk=pk, status="approved")
        tp, _  = TechnicalProfile.objects.get_or_create(player=player)

        # جمع‌آوری trait_id های تیک‌خورده
        checked_ids = set()
        for key in request.POST:
            if key.startswith("trait_"):
                try:
                    checked_ids.add(int(key.split("_")[1]))
                except (ValueError, IndexError):
                    pass

        all_types = SoftTraitType.objects.filter(is_active=True)
        for tt in all_types:
            if tt.pk in checked_ids:
                PlayerSoftTrait.objects.update_or_create(
                    technical_profile=tp,
                    trait_type_id=tt.pk,
                    defaults={"score": 1, "evaluated_by": request.user},
                )
            else:
                PlayerSoftTrait.objects.filter(
                    technical_profile=tp, trait_type_id=tt.pk
                ).delete()
        from ..models import PlayerChangeLog
        from ..views.player_edit_views import _notify_about_player_change
        PlayerChangeLog.objects.create(
            player=player, changed_by=request.user,
            change_type=PlayerChangeLog.ChangeType.SOFT_TRAITS,
            description="ویرایش ویژگی‌های نرم",
        )
        _notify_about_player_change(request.user, player, "ویرایش ویژگی‌های نرم 🧠")

        try:
            from ..services.activity_service import log_player_change
            from ..models import PlayerActivityLog
            log_player_change(
                player=player, actor=request.user,
                action=PlayerActivityLog.ActionType.TRAITS_UPDATED,
            )
        except Exception:
            pass
        messages.success(request, "ویژگی‌های نرم ذخیره شد.")
        return redirect("training:player-profile", pk=pk)


class SoftTraitTypeView(LoginRequiredMixin, RoleRequiredMixin, View):
    """
    GET  → لیست انواع ویژگی نرم
    POST → ایجاد نوع جدید
    """
    allowed_roles = ["is_technical_director"]

    def get(self, request):
        from ..models import SoftTraitType
        from django.shortcuts import render
        traits = SoftTraitType.objects.order_by("name")
        return render(request, "training/soft_trait_types.html", {"traits": traits})

    def post(self, request):
        from ..models import SoftTraitType
        name = request.POST.get("name", "").strip()
        desc = request.POST.get("description", "").strip()
        if name:
            SoftTraitType.objects.get_or_create(
                name=name,
                defaults={"description": desc, "created_by": request.user}
            )
            messages.success(request, f"ویژگی «{name}» اضافه شد.")
        return redirect("training:soft-trait-types")


class SoftTraitTypeDeleteView(LoginRequiredMixin, RoleRequiredMixin, View):
    """حذف یک نوع ویژگی نرم"""
    allowed_roles     = ["is_technical_director"]
    http_method_names = ["post"]

    def post(self, request, pk):
        from ..models import SoftTraitType
        obj = get_object_or_404(SoftTraitType, pk=pk)
        obj.is_active = False
        obj.save()
        messages.success(request, f"ویژگی «{obj.name}» غیرفعال شد.")
        return redirect("training:soft-trait-types")


# ══════════════════════════════════════════════════════════════════
#  مدیریت زمان‌بندی تمرین (TrainingSchedule)
# ══════════════════════════════════════════════════════════════════

class ScheduleManageView(LoginRequiredMixin, RoleRequiredMixin, View):
    """
    مدیریت جلسات تمرینی یک دسته — بدون نیاز به ادمین.
    GET  → صفحه مدیریت (در category_detail)
    POST → افزودن یک جلسه
    """
    allowed_roles = ["is_technical_director"]

    def post(self, request, cat_pk):
        from ..models import TrainingSchedule
        cat = get_object_or_404(TrainingCategory, pk=cat_pk, is_active=True)
        weekday    = request.POST.get("weekday", "").strip()
        start_time = request.POST.get("start_time", "").strip()
        end_time   = request.POST.get("end_time", "").strip() or None
        location   = request.POST.get("location", "").strip()

        if weekday and start_time:
            obj, created = TrainingSchedule.objects.get_or_create(
                category=cat,
                weekday=weekday,
                start_time=start_time,
                defaults={"end_time": end_time, "location": location},
            )
            if created:
                messages.success(request, f"جلسه {obj.get_weekday_display()} {start_time} اضافه شد.")
            else:
                messages.info(request, "این جلسه قبلاً ثبت شده.")
        else:
            messages.error(request, "روز و ساعت شروع الزامی است.")

        return redirect("training:category-detail", pk=cat_pk)


class ScheduleDeleteView(LoginRequiredMixin, RoleRequiredMixin, View):
    """حذف یک جلسه تمرینی"""
    allowed_roles     = ["is_technical_director"]
    http_method_names = ["post"]

    def post(self, request, pk):
        from ..models import TrainingSchedule
        sch = get_object_or_404(TrainingSchedule, pk=pk)
        cat_pk = sch.category.pk
        sch.delete()
        messages.success(request, "جلسه حذف شد.")
        return redirect("training:category-detail", pk=cat_pk)