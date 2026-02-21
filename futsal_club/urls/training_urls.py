"""
futsal_club/urls/training_urls.py
─────────────────────────────────────────────────────────────────────
namespace = "training"

URL های مربوط به:
  - دسته‌های آموزشی
  - مربیان
  - انتخاب دسته برای حضور و غیاب
  - لیست و پروفایل بازیکنان
"""
from django.urls import path
from ..views.category_views import (
    # دسته‌های آموزشی
    CategoryListView,
    CategoryCreateView,
    CategoryUpdateView,
    CategoryDetailView,
    CategoryToggleActiveView,
    # مربیان
    CoachListView,
    CoachCreateView,
    CoachUpdateView,
    CoachDetailView,
    CoachToggleActiveView,
    # حضور و غیاب
    AttendanceCategorySelectView,
    # بازیکنان
    PlayerListView,
    PlayerProfileView,
)

app_name = "training"

urlpatterns = [
    # ── دسته‌های آموزشی ──────────────────────────────────────────
    path("categories/",
         CategoryListView.as_view(),         name="category-list"),
    path("categories/create/",
         CategoryCreateView.as_view(),        name="category-create"),
    path("categories/<int:pk>/",
         CategoryDetailView.as_view(),        name="category-detail"),
    path("categories/<int:pk>/edit/",
         CategoryUpdateView.as_view(),        name="category-update"),
    path("categories/<int:pk>/toggle/",
         CategoryToggleActiveView.as_view(),  name="category-toggle"),

    # ── مربیان ───────────────────────────────────────────────────
    path("coaches/",
         CoachListView.as_view(),             name="coach-list"),
    path("coaches/create/",
         CoachCreateView.as_view(),           name="coach-create"),
    path("coaches/<int:pk>/",
         CoachDetailView.as_view(),           name="coach-detail"),
    path("coaches/<int:pk>/edit/",
         CoachUpdateView.as_view(),           name="coach-update"),
    path("coaches/<int:pk>/toggle/",
         CoachToggleActiveView.as_view(),     name="coach-toggle"),

    # ── انتخاب دسته برای حضور و غیاب ─────────────────────────────
    path("attendance/",
         AttendanceCategorySelectView.as_view(), name="attendance-select"),

    # ── بازیکنان ─────────────────────────────────────────────────
    path("players/",
         PlayerListView.as_view(),            name="player-list"),
    path("players/<int:pk>/",
         PlayerProfileView.as_view(),         name="player-profile"),
    path("profile/",
         PlayerProfileView.as_view(),         name="my-profile"),
]
