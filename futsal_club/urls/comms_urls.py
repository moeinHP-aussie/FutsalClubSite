"""
futsal_club/urls/comms_urls.py
namespace = "comms"
"""
from django.urls import path

from ..views.announcement_views import (
    AnnouncementListView,
    AnnouncementCreateView,
    AnnouncementDeleteView,
    NotificationListView,
    NotificationMarkReadView,
    NotificationMarkAllReadView,
)

app_name = "comms"

urlpatterns = [
    # ── اطلاعیه‌ها ───────────────────────────────────────────────────
    path("announcements/",            AnnouncementListView.as_view(),   name="announcement-list"),
    path("announcements/create/",     AnnouncementCreateView.as_view(), name="announcement-create"),
    path("announcements/<int:pk>/delete/", AnnouncementDeleteView.as_view(), name="announcement-delete"),

    # ── اعلان‌ها (notifications) ──────────────────────────────────────
    path("notifications/",                    NotificationListView.as_view(),       name="notification-list"),
    path("notifications/<int:pk>/read/",      NotificationMarkReadView.as_view(),   name="notification-read"),
    path("notifications/read-all/",           NotificationMarkAllReadView.as_view(), name="notification-read-all"),
]