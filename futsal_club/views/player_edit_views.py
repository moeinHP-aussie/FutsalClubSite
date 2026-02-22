"""
futsal_club/views/player_edit_views.py
─────────────────────────────────────────────────────────────────────
ویرایش اطلاعات بازیکن و آپلود تصویر بیمه
"""
from django import forms
from django.contrib import messages
from django.contrib.auth.mixins import LoginRequiredMixin
from django.core.exceptions import PermissionDenied
from django.shortcuts import get_object_or_404, redirect
from django.views import View
from django.views.generic import UpdateView
from django.urls import reverse_lazy, reverse

import jdatetime

from ..mixins import RoleRequiredMixin
from ..models import Player


# ──────────────────────────────────────────────────────────────────
#  فرم ویرایش بازیکن (مربی / مدیر فنی)
# ──────────────────────────────────────────────────────────────────
class PlayerEditForm(forms.ModelForm):
    """
    فرم ویرایش اطلاعات بازیکن.
    شامل تاریخ بیمه شمسی به صورت رشته.
    """
    insurance_expiry_jalali = forms.CharField(
        label="تاریخ انقضای بیمه (شمسی)",
        required=False,
        widget=forms.TextInput(attrs={"placeholder": "مثال: ۱۴۰۴/۰۶/۳۰", "dir": "ltr"}),
    )

    class Meta:
        model  = Player
        fields = [
            "first_name", "last_name", "father_name",
            "phone", "father_phone", "mother_phone",
            "address",
            "height", "weight",
            "preferred_hand", "preferred_foot",
            "medical_history", "injury_history",
            "insurance_status",
            "father_education", "father_job",
            "mother_education", "mother_job",
        ]
        widgets = {
            "address":        forms.Textarea(attrs={"rows": 2}),
            "medical_history":forms.Textarea(attrs={"rows": 2}),
            "injury_history": forms.Textarea(attrs={"rows": 2}),
        }
        labels = {
            "first_name":       "نام",
            "last_name":        "نام خانوادگی",
            "father_name":      "نام پدر",
            "phone":            "موبایل بازیکن",
            "father_phone":     "موبایل پدر",
            "mother_phone":     "موبایل مادر",
            "address":          "آدرس",
            "height":           "قد (سانتی‌متر)",
            "weight":           "وزن (کیلوگرم)",
            "preferred_hand":   "دست برتر",
            "preferred_foot":   "پای برتر",
            "medical_history":  "سابقه پزشکی",
            "injury_history":   "سابقه آسیب‌دیدگی",
            "insurance_status": "وضعیت بیمه",
            "father_education": "تحصیلات پدر",
            "father_job":       "شغل پدر",
            "mother_education": "تحصیلات مادر",
            "mother_job":       "شغل مادر",
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # اگه تاریخ بیمه موجوده، به شمسی تبدیل کن
        if self.instance and self.instance.pk and self.instance.insurance_expiry_date:
            try:
                jd = self.instance.insurance_expiry_date
                self.fields["insurance_expiry_jalali"].initial = (
                    f"{jd.year}/{jd.month:02d}/{jd.day:02d}"
                )
            except Exception:
                pass

    def clean_insurance_expiry_jalali(self):
        raw = self.cleaned_data.get("insurance_expiry_jalali", "").strip()
        if not raw:
            return None
        # تبدیل اعداد فارسی
        for fa, en in zip("۰۱۲۳۴۵۶۷۸۹", "0123456789"):
            raw = raw.replace(fa, en)
        try:
            parts = [int(p) for p in raw.replace("-", "/").split("/")]
            return jdatetime.date(*parts)   # jDateField انتظار jdatetime.date دارد
        except Exception:
            raise forms.ValidationError("تاریخ معتبر وارد کنید. فرمت: ۱۴۰۴/۰۶/۳۰")


class PlayerEditView(LoginRequiredMixin, View):
    """
    ویرایش اطلاعات بازیکن توسط مربی یا مدیر فنی.
    مربی فقط بازیکنان دسته‌های خودش رو می‌تونه ویرایش کنه.
    """
    template_name = "registration/player_edit.html"

    def _get_player(self, pk, user):
        player = get_object_or_404(Player, pk=pk, is_archived=False)
        if user.is_superuser or user.is_technical_director:
            return player
        # مربی: فقط دسته‌های خودش
        if user.is_coach:
            try:
                coach = user.coach_profile
                if player.categories.filter(coaches=coach).exists():
                    return player
            except Exception:
                pass
        raise PermissionDenied

    def get(self, request, pk):
        player = self._get_player(pk, request.user)
        form   = PlayerEditForm(instance=player)
        return self._render(request, player, form)

    def post(self, request, pk):
        player = self._get_player(pk, request.user)
        form   = PlayerEditForm(request.POST, instance=player)
        if form.is_valid():
            obj = form.save(commit=False)
            # ذخیره تاریخ بیمه شمسی
            jdate = form.cleaned_data.get("insurance_expiry_jalali")
            if jdate is not None:
                obj.insurance_expiry_date = jdate
            obj.save()
            messages.success(request, f"اطلاعات {player} بروزرسانی شد.")
            return redirect("training:player-profile", pk=player.pk)
        return self._render(request, player, form)

    def _render(self, request, player, form):
        from django.shortcuts import render
        return render(request, self.template_name, {"player": player, "form": form})


# ──────────────────────────────────────────────────────────────────
#  آپلود تصویر بیمه توسط بازیکن
# ──────────────────────────────────────────────────────────────────
class InsuranceImageUploadView(LoginRequiredMixin, View):
    """
    بازیکن می‌تواند تصویر بیمه‌نامه خود را آپلود کند.
    مربی / مدیر فنی هم می‌توانند برای هر بازیکن آپلود کنند.
    """

    def _get_player(self, pk, user):
        player = get_object_or_404(Player, pk=pk, is_archived=False)
        # خود بازیکن
        if hasattr(user, "player_profile") and user.player_profile == player:
            return player
        # مربی یا مدیر فنی
        if user.is_technical_director or user.is_superuser:
            return player
        if user.is_coach:
            try:
                coach = user.coach_profile
                if player.categories.filter(coaches=coach).exists():
                    return player
            except Exception:
                pass
        raise PermissionDenied

    def post(self, request, pk):
        player = self._get_player(pk, request.user)
        img    = request.FILES.get("insurance_image")
        if not img:
            messages.error(request, "لطفاً یک تصویر انتخاب کنید.")
        else:
            # حذف تصویر قدیمی
            if player.insurance_image:
                try:
                    player.insurance_image.delete(save=False)
                except Exception:
                    pass
            player.insurance_image   = img
            player.insurance_status  = Player.InsuranceStatus.ACTIVE
            player.save(update_fields=["insurance_image", "insurance_status"])
            messages.success(request, "تصویر بیمه‌نامه با موفقیت آپلود شد.")

        # ریدایرکت به پروفایل
        if request.user.is_coach or request.user.is_technical_director:
            return redirect("training:player-profile", pk=player.pk)
        return redirect("training:my-profile")


def _notify_about_player_change(changed_by, player, change_desc):
    """
    اعلان تغییر بازیکن به مربیان و مدیر فنی.
    - اگر مربی تغییر داد: مدیر فنی را خبر کن
    - اگر مدیر فنی تغییر داد: مربیان آن بازیکن را خبر کن
    - اگر خود بازیکن تغییر داد: مربیان + مدیر فنی را خبر کن
    """
    from ..models import Notification, Coach, CustomUser

    player_name = f"{player.first_name} {player.last_name}"
    actor_name  = changed_by.get_full_name() or changed_by.username

    msg = f"تغییر در اطلاعات بازیکن {player_name}: {change_desc}\nتوسط: {actor_name}"

    recipients = set()

    # مدیر فنی همیشه باید خبر بگیره (مگر اینکه خودش تغییر داده باشه)
    if not changed_by.is_technical_director:
        tds = CustomUser.objects.filter(is_technical_director=True, is_active=True)
        for td in tds:
            recipients.add(td.pk)

    # مربیان آن بازیکن باید خبر بگیرن (مگر اینکه خود مربی تغییر داده باشه)
    if not changed_by.is_coach:
        cat_ids = player.categories.values_list("pk", flat=True)
        coach_users = CustomUser.objects.filter(
            coach_profile__category_rates__category__in=cat_ids,
            is_active=True,
        ).distinct()
        for cu in coach_users:
            recipients.add(cu.pk)

    for uid in recipients:
        try:
            u = CustomUser.objects.get(pk=uid)
            Notification.objects.create(
                recipient=u,
                type=Notification.NotificationType.PLAYER_CHANGE,
                title=f"تغییر اطلاعات بازیکن: {player_name}",
                message=msg,
                related_player=player,
            )
        except Exception:
            pass