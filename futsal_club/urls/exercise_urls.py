"""
futsal_club/urls/exercise_urls.py
namespace = "exercises"
"""
from django.urls import path

from ..views.exercise_views import (
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
