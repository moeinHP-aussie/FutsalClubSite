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
    CreateView, DetailView, ListView, TemplateView, UpdateView, View,
)
from django.utils.translation import gettext_lazy as _

from ..mixins import RoleRequiredMixin
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
            # بازیکن پروفایل خودش رو می‌بینه
            try:
                player = self.request.user.player_profile
            except Player.DoesNotExist:
                player = None

        ctx["player"]     = player
        if player:
            ctx["categories"] = player.categories.filter(is_active=True)
            # آخرین فاکتورها
            ctx["recent_invoices"] = player.invoices.order_by(
                "-created_at"
            )[:5] if hasattr(player, "invoices") else []
        return ctx


class PlayerListView(LoginRequiredMixin, RoleRequiredMixin, ListView):
    """لیست بازیکنان تأیید‌شده با قابلیت فیلتر"""
    model = Player
    template_name = "training/player_list.html"
    context_object_name = "players"
    paginate_by = 25
    allowed_roles = ["is_technical_director", "is_coach", "is_finance_manager"]

    def get_queryset(self):
        qs = Player.objects.filter(status="approved").order_by("last_name", "first_name")
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
        return qs

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx["q"]              = self.request.GET.get("q", "")
        ctx["category_filter"]= self.request.GET.get("category", "")
        ctx["all_categories"] = TrainingCategory.objects.filter(is_active=True).order_by("name")
        ctx["total_count"]    = Player.objects.filter(status="approved").count()
        return ctx
