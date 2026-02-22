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
from ..views.organize_views import OrganizeView, PlayerMoveView, StatsView
from ..views.category_views import (
    # دسته‌های آموزشی
    CategoryListView,
    CategoryDeleteView,
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
    # پروفایل فنی + ویژگی نرم + زمان‌بندی
    TechnicalProfileUpdateView,
    SoftTraitUpdateView,
    SoftTraitTypeView,
    SoftTraitTypeDeleteView,
    ScheduleManageView,
    ScheduleDeleteView,
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
    path("categories/<int:pk>/delete/",
         CategoryDeleteView.as_view(),        name="category-delete"),

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

    # ── پروفایل فنی بازیکن ──────────────────────────────────────
    path("players/<int:pk>/tech/",
         TechnicalProfileUpdateView.as_view(), name="tech-profile-update"),
    path("players/<int:pk>/soft-traits/",
         SoftTraitUpdateView.as_view(),        name="soft-traits-update"),
    path("soft-trait-types/",
         SoftTraitTypeView.as_view(),          name="soft-trait-types"),
    path("soft-trait-types/<int:pk>/delete/",
         SoftTraitTypeDeleteView.as_view(),    name="soft-trait-type-delete"),

    # ── زمان‌بندی تمرین ─────────────────────────────────────────
    path("categories/<int:cat_pk>/schedule/add/",
         ScheduleManageView.as_view(),         name="schedule-add"),
    path("schedules/<int:pk>/delete/",
         ScheduleDeleteView.as_view(),         name="schedule-delete"),

    # ── سازماندهی رده‌ها ─────────────────────────────────────────
    path("organize/",
         OrganizeView.as_view(),              name="organize"),
    path("organize/move/",
         PlayerMoveView.as_view(),            name="player-move"),

    # ── آمارگیری ─────────────────────────────────────────────────
    path("stats/",
         StatsView.as_view(),                 name="stats"),
]