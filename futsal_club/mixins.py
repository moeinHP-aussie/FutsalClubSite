"""
mixins.py
─────────────────────────────────────────────────────────────────────
میکسین‌های دسترسی نقش‌محور (RBAC)
"""

from django.contrib.auth.mixins import AccessMixin
from django.core.exceptions import PermissionDenied
from django.utils.translation import gettext_lazy as _


class RoleRequiredMixin(AccessMixin):
    """
    بررسی می‌کند که کاربر حداقل یکی از نقش‌های allowed_roles را داشته باشد.

    class MyView(RoleRequiredMixin, TemplateView):
        allowed_roles = ["is_coach", "is_technical_director"]
    """
    allowed_roles: list[str] = []

    def dispatch(self, request, *args, **kwargs):
        if not request.user.is_authenticated:
            return self.handle_no_permission()

        if request.user.is_superuser:
            return super().dispatch(request, *args, **kwargs)

        if not self.allowed_roles:
            return super().dispatch(request, *args, **kwargs)

        has_role = any(getattr(request.user, role, False) for role in self.allowed_roles)
        if not has_role:
            raise PermissionDenied(
                _("شما دسترسی لازم برای این صفحه را ندارید.")
            )

        return super().dispatch(request, *args, **kwargs)
