"""
apps.py  —  App configuration with signal registration
"""
from django.apps import AppConfig


class FutsalClubConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name               = "futsal_club"
    verbose_name       = "سیستم مدیریت باشگاه فوتسال اسپاد"

    def ready(self):
        import futsal_club.signals  # noqa: F401  ← registers all signals


# ══════════════════════════════════════════════════════════════════════
#  registration_urls.py   namespace="registration"
# ══════════════════════════════════════════════════════════════════════
REGISTRATION_URLCONF = """
from django.urls import path
from .views.registration_views import (
    ApplicantRegistrationView,
    RegistrationSuccessView,
    ApplicantListView,
    ApplicantDetailView,
    ApproveApplicantView,
    RejectApplicantView,
    ArchivePlayerView,
    ArchivedPlayerListView,
    RestorePlayerView,
)

app_name = "registration"

urlpatterns = [
    # ─── عمومی (بدون نیاز به لاگین) ───────────────────────────────
    path("apply/",          ApplicantRegistrationView.as_view(), name="apply"),
    path("apply/success/",  RegistrationSuccessView.as_view(),   name="success"),

    # ─── مدیر فنی ──────────────────────────────────────────────────
    path("applicants/",                      ApplicantListView.as_view(),   name="applicant-list"),
    path("applicants/<int:pk>/",             ApplicantDetailView.as_view(), name="applicant-detail"),
    path("applicants/<int:pk>/approve/",     ApproveApplicantView.as_view(),name="approve"),
    path("applicants/<int:pk>/reject/",      RejectApplicantView.as_view(), name="reject"),

    # ─── آرشیو ─────────────────────────────────────────────────────
    path("players/<int:pk>/archive/",        ArchivePlayerView.as_view(),   name="archive-player"),
    path("players/archived/",               ArchivedPlayerListView.as_view(), name="archived-players"),
    path("players/<int:pk>/restore/",       RestorePlayerView.as_view(),   name="restore-player"),
]
"""

# ══════════════════════════════════════════════════════════════════════
#  exercise_urls.py   namespace="exercises"
# ══════════════════════════════════════════════════════════════════════
EXERCISE_URLCONF = """
from django.urls import path
from .views.exercise_views import (
    ExerciseListView,
    ExerciseUploadView,
    ExerciseDetailView,
    ExerciseDownloadView,
    ExerciseDeleteView,
)

app_name = "exercises"

urlpatterns = [
    path("",              ExerciseListView.as_view(),    name="gallery"),
    path("upload/",       ExerciseUploadView.as_view(),  name="upload"),
    path("<int:pk>/",     ExerciseDetailView.as_view(),  name="detail"),
    path("<int:pk>/dl/",  ExerciseDownloadView.as_view(),name="download"),
    path("<int:pk>/del/", ExerciseDeleteView.as_view(),  name="delete"),
]
"""
