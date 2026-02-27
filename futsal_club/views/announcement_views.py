"""
views/announcement_views.py
─────────────────────────────────────────────────────────────────────
ویوهای اطلاعیه و اعلان
"""
from __future__ import annotations
from django.contrib import messages
from django.contrib.auth.mixins import LoginRequiredMixin
from django.http import JsonResponse
from django.shortcuts import redirect
from django.utils import timezone
from django.views import View
from django.views.generic import CreateView, ListView, TemplateView
from django.urls import reverse_lazy

from ..mixins import RoleRequiredMixin
from ..models import Announcement, Notification, TrainingCategory


class AnnouncementListView(LoginRequiredMixin, ListView):
    template_name       = "comms/announcement_list.html"
    context_object_name = "announcements"
    paginate_by         = 15

    def get_queryset(self):
        user = self.request.user
        qs   = Announcement.objects.prefetch_related("categories").order_by("-published_at")
        # بازیکن فقط اطلاعیه‌های دسته‌هایش را می‌بیند
        if user.is_player and not user.is_coach and not user.is_technical_director:
            try:
                player_cats = user.player_profile.categories.values_list("pk", flat=True)
                qs = qs.filter(categories__pk__in=player_cats).distinct()
            except Exception:
                qs = qs.none()
        return qs

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        if self.request.user.is_coach or self.request.user.is_technical_director:
            ctx["can_create"] = True
            ctx["my_cats"]    = TrainingCategory.objects.filter(is_active=True)
        return ctx


class AnnouncementCreateView(LoginRequiredMixin, RoleRequiredMixin, CreateView):
    allowed_roles   = ["is_coach", "is_technical_director"]
    template_name   = "comms/announcement_form.html"
    success_url     = reverse_lazy("comms:announcement-list")

    # Use raw model to avoid form import dependency
    from ..models import Announcement as _Ann
    model           = _Ann
    fields          = ["title", "body", "categories", "is_pinned"]

    def form_valid(self, form):
        form.instance.author = self.request.user
        # مربی فقط می‌تواند برای دسته‌هایش اطلاعیه بفرستد
        if self.request.user.is_coach and not self.request.user.is_technical_director:
            allowed = TrainingCategory.objects.filter(
                coachcategoryrate__coach__user=self.request.user,
                coachcategoryrate__is_active=True,
            ).values_list("pk", flat=True)
            cats = form.cleaned_data.get("categories", [])
            if any(c.pk not in allowed for c in cats):
                form.add_error("categories", "فقط می‌توانید برای دسته‌های خودتان اطلاعیه ارسال کنید.")
                return self.form_invalid(form)
        messages.success(self.request, "اطلاعیه با موفقیت ارسال شد.")
        return super().form_valid(form)

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        # محدود کردن دسته‌ها در فرم
        if self.request.user.is_coach and not self.request.user.is_technical_director:
            ctx["form"].fields["categories"].queryset = TrainingCategory.objects.filter(
                coachcategoryrate__coach__user=self.request.user,
                coachcategoryrate__is_active=True,
            )
        return ctx


class NotificationListView(LoginRequiredMixin, ListView):
    template_name       = "comms/notification_list.html"
    context_object_name = "notifications"
    paginate_by         = 20

    def get_queryset(self):
        return (
            Notification.objects
            .filter(recipient=self.request.user)
            .order_by("-created_at")
        )

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx["unread_count"] = self.get_queryset().filter(is_read=False).count()
        return ctx


class NotificationMarkReadView(LoginRequiredMixin, View):
    def get(self, request, pk: int):
        notif = Notification.objects.filter(pk=pk, recipient=request.user).first()
        if notif: notif.mark_as_read()
        next_url = request.GET.get("next", "comms:notification-list")
        return redirect(next_url)


class NotificationMarkAllReadView(LoginRequiredMixin, View):
    http_method_names = ["post"]
    def post(self, request):
        Notification.objects.filter(recipient=request.user, is_read=False).update(
            is_read=True, read_at=timezone.now()
        )
        if request.headers.get("x-requested-with") == "XMLHttpRequest":
            return JsonResponse({"success": True})
        return redirect("comms:notification-list")


class AnnouncementDeleteView(LoginRequiredMixin, View):
    """حذف اطلاعیه — فقط توسط نویسنده یا مدیر فنی"""

    def post(self, request, pk: int):
        ann = Announcement.objects.filter(pk=pk).first()
        if not ann:
            messages.error(request, "اطلاعیه پیدا نشد.")
            return redirect("comms:announcement-list")

        # فقط نویسنده یا مدیر فنی می‌تواند حذف کند
        if ann.author != request.user and not request.user.is_technical_director:
            messages.error(request, "شما اجازه حذف این اطلاعیه را ندارید.")
            return redirect("comms:announcement-list")

        title = ann.title
        ann.delete()
        messages.success(request, f"اطلاعیه «{title}» حذف شد.")
        return redirect("comms:announcement-list")