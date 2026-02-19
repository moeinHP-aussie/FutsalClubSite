"""
futsal_club/urls/attendance_urls.py
namespace = "attendance"
"""
from django.urls import path
from ..views.attendance_views import (
    AttendanceMatrixView,
    AttendanceSheetListView,
    FinalizeAttendanceSheetView,
    PlayerAttendanceHistoryView,
    RecordSessionAttendanceView,
    SessionAttendanceDetailView,
)

app_name = "attendance"

urlpatterns = [
    path(
        "category/<int:category_pk>/matrix/",
        AttendanceMatrixView.as_view(),
        name="matrix",
    ),
    path(
        "category/<int:category_pk>/sheets/",
        AttendanceSheetListView.as_view(),
        name="sheet-list",
    ),
    path(
        "session/<int:session_pk>/",
        SessionAttendanceDetailView.as_view(),
        name="session-detail",
    ),
    path(
        "session/<int:session_pk>/record/",
        RecordSessionAttendanceView.as_view(),
        name="session-record",
    ),
    path(
        "sheet/<int:sheet_pk>/finalize/",
        FinalizeAttendanceSheetView.as_view(),
        name="sheet-finalize",
    ),
    path(
        "player/<int:player_pk>/history/",
        PlayerAttendanceHistoryView.as_view(),
        name="player-history",
    ),
]