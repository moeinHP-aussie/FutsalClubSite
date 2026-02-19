"""
futsal_club/urls/auth_urls.py
namespace = "auth"
"""
from django.urls import path
from ..views.auth_views import CustomLoginView, CustomLogoutView, DashboardView, ChangePasswordView

app_name = "auth"

urlpatterns = [
    path("login/",           CustomLoginView.as_view(),   name="login"),
    path("logout/",          CustomLogoutView.as_view(),  name="logout"),
    path("dashboard/",       DashboardView.as_view(),     name="dashboard"),
    path("password/change/", ChangePasswordView.as_view(),name="password-change"),
]
