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