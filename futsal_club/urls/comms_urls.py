"""
futsal_club/urls/comms_urls.py
namespace = "comms"
"""
from django.urls import path

from ..views.announcement_views import (
    AnnouncementListView,
    AnnouncementCreateView,
    NotificationListView,
    NotificationMarkReadView,
    NotificationMarkAllReadView,
)

app_name = "comms"

urlpatterns = [
    # ── اعلانات ──────────────────────────────────────────────────────
    path("announcements/",        AnnouncementListView.as_view(),   name="announcement-list"),
    path("announcements/create/", AnnouncementCreateView.as_view(), name="announcement-create"),

    # ── اعلان‌ها (notifications) ─────────────────────────────────────
    path("notifications/",                   NotificationListView.as_view(),       name="notification-list"),
    # ✅ read-all باید قبل از <int:pk>/read/ باشد تا URL درست resolve شود
    path("notifications/read-all/",          NotificationMarkAllReadView.as_view(), name="notification-read-all"),
    path("notifications/<int:pk>/read/",     NotificationMarkReadView.as_view(),   name="notification-read"),
]