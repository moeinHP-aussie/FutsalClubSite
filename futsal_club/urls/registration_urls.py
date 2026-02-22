"""
futsal_club/urls/registration_urls.py
namespace = "registration"
"""
from django.urls import path

from ..views.registration_views import (
    ApplicantRegistrationView,
    ApproveApplicantView,
    ArchivePlayerView,
    ArchivedPlayerListView,
    ApplicantListView,
    ApplicantDetailView,
    RejectApplicantView,
    RegistrationSuccessView,
    RestorePlayerView,
    BulkPlayerActionView,
    PermanentDeletePlayerView,
)
from ..views.import_views import BulkImportView, ImportSheetPreviewView
from ..views.player_edit_views import PlayerEditView, InsuranceImageUploadView

app_name = "registration"

urlpatterns = [
    # ── عمومی (بدون نیاز به لاگین) ──────────────────────────────────
    path("apply/",         ApplicantRegistrationView.as_view(), name="apply"),
    path("apply/success/", RegistrationSuccessView.as_view(),   name="success"),

    # ── مدیر فنی: بررسی متقاضیان ──────────────────────────────────
    path("applicants/",                  ApplicantListView.as_view(),   name="applicant-list"),
    path("applicants/<int:pk>/",         ApplicantDetailView.as_view(), name="applicant-detail"),
    path("applicants/<int:pk>/approve/", ApproveApplicantView.as_view(),name="approve"),
    path("applicants/<int:pk>/reject/",  RejectApplicantView.as_view(), name="reject"),

    # ── آرشیو نرم ───────────────────────────────────────────────────
    path("players/<int:pk>/archive/",  ArchivePlayerView.as_view(),    name="archive-player"),
    path("players/archived/",          ArchivedPlayerListView.as_view(),name="archived-players"),
    path("players/<int:pk>/restore/",  RestorePlayerView.as_view(),    name="restore-player"),

    # ── ویرایش بازیکن (مربی / مدیر فنی) ────────────────────────────
    path("players/<int:pk>/edit/",
         PlayerEditView.as_view(),             name="player-edit"),
    path("players/<int:pk>/insurance-upload/",
         InsuranceImageUploadView.as_view(),   name="insurance-upload"),

    # ── عملیات دسته‌جمعی ────────────────────────────────────────────
    path("players/bulk-action/",
         BulkPlayerActionView.as_view(), name="player-bulk-action"),

    # ── سطل زباله (Recycle Bin) ──────────────────────────────────────
    path("players/recycle-bin/",
         ArchivedPlayerListView.as_view(),     name="recycle-bin"),
    path("players/<int:pk>/permanent-delete/",
         PermanentDeletePlayerView.as_view(),  name="player-permanent-delete"),

    # ── ایمپورت دسته‌جمعی ────────────────────────────────────────────
    path("import/",         BulkImportView.as_view(),         name="bulk-import"),
    path("import/preview/", ImportSheetPreviewView.as_view(), name="import-preview"),
]