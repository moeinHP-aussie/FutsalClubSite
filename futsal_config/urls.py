"""
futsal_config/urls.py
─────────────────────────────────────────────────────────────────────
Master URL Router — همه namespace ها اینجا include می‌شوند
"""
from django.contrib import admin
from django.urls import path, include
from django.conf import settings
from django.conf.urls.static import static
from django.http import JsonResponse
from django.views.generic import RedirectView


def health_check(request):
    """Docker health-check endpoint."""
    return JsonResponse({"status": "ok"})


urlpatterns = [
    # ── Admin ─────────────────────────────────────────────────────────
    path("admin/", admin.site.urls),

    # ── Health Check (برای Docker) ────────────────────────────────────
    path("health/", health_check, name="health"),

    # ── Auth ──────────────────────────────────────────────────────────
    path("auth/", include("futsal_club.urls.auth_urls", namespace="accounts")),

    # ── ثبت‌نام + مدیریت بازیکنان ─────────────────────────────────────
    path("registration/", include("futsal_club.urls.registration_urls", namespace="registration")),

    # ── حضور و غیاب ───────────────────────────────────────────────────
    path("attendance/", include("futsal_club.urls.attendance_urls", namespace="attendance")),

    # ── مالی ──────────────────────────────────────────────────────────
    path("payroll/", include("futsal_club.urls.payroll_urls", namespace="payroll")),

    # ── ارتباطات ──────────────────────────────────────────────────────
    path("comms/", include("futsal_club.urls.comms_urls", namespace="comms")),

    # ── مخزن تمرین‌ها ─────────────────────────────────────────────────
    path("exercises/", include("futsal_club.urls.exercise_urls", namespace="exercises")),

    # ── دسته‌های آموزشی، مربیان، بازیکنان ─────────────────────────────
    path("training/", include("futsal_club.urls.training_urls", namespace="training")),

    # ── ریدایرکت صفحه اصلی به لاگین ─────────────────────────────────
    path("", RedirectView.as_view(url="/auth/login/", permanent=False)),
]

# ✅ در Development فقط فایل‌های media را Django سرو می‌کند
# Static را نیازی نیست اضافه کنیم — runserver خودش از STATICFILES_DIRS سرو می‌کنه
if settings.DEBUG:
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)