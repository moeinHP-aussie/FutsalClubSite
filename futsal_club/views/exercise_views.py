"""
views/exercise_views.py
─────────────────────────────────────────────────────────────────────
مخزن تمرین‌ها — آپلود توسط مربی / مشاهده توسط مدیر فنی
"""
from __future__ import annotations

import os
import logging
import mimetypes

from django.contrib import messages
from django.contrib.auth.mixins import LoginRequiredMixin
from django.db.models import Q
from django.http import FileResponse, Http404
from django.shortcuts import get_object_or_404, redirect
from django.views import View
from django.views.generic import DeleteView, DetailView, FormView, ListView
from django.urls import reverse_lazy

from ..forms.registration_forms import ExerciseUploadForm
from ..mixins import RoleRequiredMixin
from ..models import Exercise, ExerciseTag, TrainingCategory

logger = logging.getLogger(__name__)

ALLOWED_MIME_TYPES = {
    "video":    ["video/mp4", "video/webm", "video/quicktime", "video/x-msvideo"],
    "image":    ["image/jpeg", "image/png", "image/webp", "image/heic"],
    "gif":      ["image/gif"],
    "document": ["application/pdf", "application/msword",
                 "application/vnd.openxmlformats-officedocument.wordprocessingml.document"],
}
MAX_UPLOAD_MB = 200   # حداکثر سایز فایل


class ExerciseListView(LoginRequiredMixin, RoleRequiredMixin, ListView):
    """
    گالری تمرین‌ها با فیلتر نوع رسانه، دسته، و جستجوی متنی.
    مربی: فقط تمرین‌های خودش + تمرین‌های عمومی
    مدیر فنی: همه تمرین‌ها
    """
    allowed_roles       = ["is_coach", "is_technical_director"]
    template_name       = "exercises/gallery.html"
    context_object_name = "exercises"
    paginate_by         = 20

    def get_queryset(self):
        user = self.request.user
        qs   = Exercise.objects.select_related("uploaded_by__user").prefetch_related("tags", "categories")

        if not user.is_technical_director:
            # مربی: فقط تمرین‌های خودش یا عمومی
            try:
                coach = user.coach_profile
                qs = qs.filter(Q(uploaded_by=coach) | Q(is_public=True))
            except Exception:
                qs = qs.filter(is_public=True)

        # ── فیلترها ─────────────────────────────────────────────
        media_type = self.request.GET.get("type")
        if media_type in ("video", "image", "gif", "document"):
            qs = qs.filter(media_type=media_type)

        cat_pk = self.request.GET.get("category")
        if cat_pk:
            qs = qs.filter(categories__pk=cat_pk)

        tag = self.request.GET.get("tag")
        if tag:
            qs = qs.filter(tags__name__icontains=tag)

        q = self.request.GET.get("q", "").strip()
        if q:
            qs = qs.filter(Q(title__icontains=q) | Q(description__icontains=q))

        return qs.order_by("-created_at")

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx.update({
            "categories":    TrainingCategory.objects.filter(is_active=True),
            "tags":          ExerciseTag.objects.all()[:30],
            "media_filter":  self.request.GET.get("type", ""),
            "cat_filter":    self.request.GET.get("category", ""),
            "tag_filter":    self.request.GET.get("tag", ""),
            "search_query":  self.request.GET.get("q", ""),
            "total_count":   self.get_queryset().count(),
            "can_upload":    self.request.user.is_coach or self.request.user.is_technical_director,
            "media_types":   [("video","ویدیو 🎬"), ("image","تصویر 🖼️"), ("gif","گیف ✨"), ("document","سند 📄")],
        })
        return ctx


class ExerciseUploadView(LoginRequiredMixin, RoleRequiredMixin, View):
    """
    آپلود تمرین جدید توسط مربی.
    GET → فرم آپلود
    POST → ذخیره فایل و رکورد
    """
    allowed_roles = ["is_coach", "is_technical_director"]
    template_name = "exercises/upload.html"

    def get(self, request):
        coach = getattr(request.user, "coach_profile", None)
        form  = ExerciseUploadForm(coach=coach)
        return self._render(request, form)

    def post(self, request):
        coach = getattr(request.user, "coach_profile", None)
        form  = ExerciseUploadForm(request.POST, request.FILES, coach=coach)

        if not form.is_valid():
            return self._render(request, form)

        data = form.cleaned_data

        # ── اعتبارسنجی نوع و سایز فایل ──────────────────────────
        uploaded_file = data["file"]
        mime, _       = mimetypes.guess_type(uploaded_file.name)
        allowed       = ALLOWED_MIME_TYPES.get(data["media_type"], [])
        if mime not in allowed:
            form.add_error("file", f"نوع فایل مجاز نیست. فرمت‌های قابل قبول: {', '.join(allowed)}")
            return self._render(request, form)

        size_mb = uploaded_file.size / (1024 * 1024)
        if size_mb > MAX_UPLOAD_MB:
            form.add_error("file", f"حجم فایل بیشتر از {MAX_UPLOAD_MB} مگابایت است.")
            return self._render(request, form)

        # ── ایجاد رکورد ──────────────────────────────────────────
        exercise = Exercise.objects.create(
            title            = data["title"],
            description      = data.get("description", ""),
            media_type       = data["media_type"],
            file             = uploaded_file,
            thumbnail        = data.get("thumbnail"),
            uploaded_by      = coach,
            duration_minutes = data.get("duration_minutes"),
            is_public        = data.get("is_public", False),
        )

        cat_ids = data.get("categories", [])
        if cat_ids:
            exercise.categories.set(TrainingCategory.objects.filter(pk__in=cat_ids))

        logger.info("تمرین جدید آپلود شد: %s توسط %s", exercise.title, request.user)
        messages.success(request, f"تمرین «{exercise.title}» با موفقیت آپلود شد.")
        return redirect("exercises:gallery")

    def _render(self, request, form):
        from django.shortcuts import render
        return render(request, self.template_name, {"form": form})


class ExerciseDetailView(LoginRequiredMixin, RoleRequiredMixin, DetailView):
    """نمایش جزئیات و پیش‌نمایش یک تمرین."""
    allowed_roles       = ["is_coach", "is_technical_director"]
    template_name       = "exercises/detail.html"
    context_object_name = "exercise"

    def get_queryset(self):
        user = self.request.user
        qs   = Exercise.objects.select_related("uploaded_by__user").prefetch_related("tags", "categories")
        if not user.is_technical_director:
            try:
                coach = user.coach_profile
                return qs.filter(Q(uploaded_by=coach) | Q(is_public=True))
            except Exception:
                return qs.filter(is_public=True)
        return qs


class ExerciseDownloadView(LoginRequiredMixin, RoleRequiredMixin, View):
    """
    دانلود فایل تمرین.
    مدیر فنی: همه فایل‌ها
    مربی: فایل‌های خودش + عمومی
    """
    allowed_roles = ["is_coach", "is_technical_director"]

    def get(self, request, pk: int):
        exercise = get_object_or_404(Exercise, pk=pk)
        user     = request.user

        # ── بررسی دسترسی ──────────────────────────────────────────
        if not user.is_technical_director:
            try:
                coach = user.coach_profile
            except Exception:
                raise Http404
            if not exercise.is_public and exercise.uploaded_by != coach:
                raise Http404

        if not exercise.file:
            raise Http404("فایل موجود نیست.")

        file_path = exercise.file.path
        if not os.path.exists(file_path):
            raise Http404("فایل روی سرور یافت نشد.")

        mime, _ = mimetypes.guess_type(file_path)
        response = FileResponse(
            open(file_path, "rb"),
            content_type=mime or "application/octet-stream",
            as_attachment=True,
            filename=os.path.basename(file_path),
        )
        logger.info("دانلود تمرین: %s توسط %s", exercise.title, request.user)
        return response


class ExerciseDeleteView(LoginRequiredMixin, RoleRequiredMixin, DeleteView):
    """حذف تمرین — فقط توسط سازنده یا مدیر فنی."""
    allowed_roles = ["is_coach", "is_technical_director"]
    template_name = "exercises/confirm_delete.html"
    success_url   = reverse_lazy("exercises:gallery")

    def get_queryset(self):
        user = self.request.user
        if user.is_technical_director:
            return Exercise.objects.all()
        try:
            return Exercise.objects.filter(uploaded_by=user.coach_profile)
        except Exception:
            return Exercise.objects.none()

    def form_valid(self, form):
        obj = self.get_object()
        messages.success(self.request, f"تمرین «{obj.title}» حذف شد.")
        return super().form_valid(form)
