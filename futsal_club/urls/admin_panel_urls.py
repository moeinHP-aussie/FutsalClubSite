"""
futsal_club/urls/admin_panel_urls.py
namespace = "admin_panel"
"""
from django.urls import path
from ..views.user_management_views import (
    UserListView,
    UserCreateView,
    UserEditView,
    ProvisionPlayerAccountsView,
    ProvisionResultView,
    DownloadCredentialsView,
)

app_name = "admin_panel"

urlpatterns = [
    path("",                      UserListView.as_view(),               name="user-list"),
    path("users/create/",         UserCreateView.as_view(),             name="user-create"),
    path("users/<str:pk>/edit/",  UserEditView.as_view(),               name="user-edit"),
    path("players/provision/",    ProvisionPlayerAccountsView.as_view(),name="provision-players"),
    path("players/provision/result/", ProvisionResultView.as_view(),    name="provision-result"),
    path("players/credentials/",  DownloadCredentialsView.as_view(),    name="download-credentials"),
]