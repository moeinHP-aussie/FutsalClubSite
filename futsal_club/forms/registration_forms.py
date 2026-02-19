"""
forms/registration_forms.py
─────────────────────────────────────────────────────────────────────
فرم‌های ثبت‌نام بازیکن و پروفایل فنی با اعتبارسنجی کامل
"""
from __future__ import annotations

from django import forms
from django.core.validators import RegexValidator
from django.utils.translation import gettext_lazy as _

from django_jalali.forms import jDateField

from ..models import Player, TechnicalProfile


PHONE_VALIDATOR = RegexValidator(
    regex=r'^09\d{9}$',
    message=_('شماره موبایل باید ۱۱ رقم بوده و با ۰۹ شروع شود.')
)
NID_VALIDATOR = RegexValidator(
    regex=r'^\d{10}$',
    message=_('کد ملی باید دقیقاً ۱۰ رقم عددی باشد.')
)


class ApplicantRegistrationForm(forms.Form):
    """
    فرم ثبت‌نام عمومی برای متقاضیان جدید.
    تمام فیلدهای اجباری مدل Player.
    """

    # ─── اطلاعات شخصی ────────────────────────────────────────────
    first_name = forms.CharField(
        label=_('نام'), max_length=100,
        widget=forms.TextInput(attrs={"placeholder": "نام خود را وارد کنید"})
    )
    last_name = forms.CharField(
        label=_('نام خانوادگی'), max_length=100,
        widget=forms.TextInput(attrs={"placeholder": "نام خانوادگی"})
    )
    father_name = forms.CharField(
        label=_('نام پدر'), max_length=100,
        widget=forms.TextInput(attrs={"placeholder": "نام پدر"})
    )
    national_id = forms.CharField(
        label=_('کد ملی'), max_length=10, min_length=10,
        validators=[NID_VALIDATOR],
        widget=forms.TextInput(attrs={"placeholder": "۱۰ رقم بدون خط تیره", "maxlength": "10", "inputmode": "numeric"})
    )
    dob = jDateField(
        label=_('تاریخ تولد (شمسی)'),
        input_formats=['%Y/%m/%d', '%Y-%m-%d'],
        widget=forms.TextInput(attrs={"placeholder": "مثال: ۱۳۸۰/۰۶/۱۵"})
    )

    # ─── تماس ────────────────────────────────────────────────────
    phone = forms.CharField(
        label=_('شماره موبایل'), max_length=11,
        validators=[PHONE_VALIDATOR],
        widget=forms.TextInput(attrs={"placeholder": "09xxxxxxxxx", "inputmode": "numeric"})
    )
    father_phone = forms.CharField(
        label=_('موبایل پدر'), max_length=11,
        validators=[PHONE_VALIDATOR],
        widget=forms.TextInput(attrs={"placeholder": "09xxxxxxxxx", "inputmode": "numeric"})
    )
    mother_phone = forms.CharField(
        label=_('موبایل مادر'), max_length=11,
        validators=[PHONE_VALIDATOR],
        required=False,
        widget=forms.TextInput(attrs={"placeholder": "09xxxxxxxxx (اختیاری)", "inputmode": "numeric"})
    )
    address = forms.CharField(
        label=_('آدرس'), required=False,
        widget=forms.Textarea(attrs={"rows": 2, "placeholder": "آدرس کامل (اختیاری)"})
    )

    # ─── بیومتریک ─────────────────────────────────────────────────
    height = forms.IntegerField(
        label=_('قد (سانتی‌متر)'), required=False, min_value=50, max_value=250,
        widget=forms.NumberInput(attrs={"placeholder": "مثال: 175", "inputmode": "numeric"})
    )
    weight = forms.DecimalField(
        label=_('وزن (کیلوگرم)'), required=False, min_value=20, max_value=300,
        decimal_places=1,
        widget=forms.NumberInput(attrs={"placeholder": "مثال: 70.5", "inputmode": "decimal"})
    )
    preferred_hand = forms.ChoiceField(
        label=_('دست برتر'),
        choices=Player.HandPreference.choices,
        initial='R'
    )
    preferred_foot = forms.ChoiceField(
        label=_('پای برتر'),
        choices=Player.FootPreference.choices,
        initial='R'
    )
    medical_history = forms.CharField(
        label=_('سابقه پزشکی'), required=False,
        widget=forms.Textarea(attrs={"rows": 2, "placeholder": "بیماری خاص، دارو مصرفی، ... (اختیاری)"})
    )
    injury_history = forms.CharField(
        label=_('سابقه مصدومیت'), required=False,
        widget=forms.Textarea(attrs={"rows": 2, "placeholder": "آسیب‌های قبلی (اختیاری)"})
    )

    # ─── اطلاعات خانوادگی ─────────────────────────────────────────
    father_education = forms.ChoiceField(
        label=_('تحصیلات پدر'),
        choices=[('', '--- انتخاب کنید ---')] + [
            ('illiterate', 'بی‌سواد'),
            ('high_school', 'دیپلم'),
            ('associate', 'فوق دیپلم'), ('bachelor', 'لیسانس'),
            ('master', 'فوق لیسانس'), ('phd', 'دکترا'),
        ],
        required=False
    )
    father_job = forms.CharField(
        label=_('شغل پدر'), max_length=150, required=False,
        widget=forms.TextInput(attrs={"placeholder": "شغل پدر"})
    )
    mother_education = forms.ChoiceField(
        label=_('تحصیلات مادر'),
        choices=[('', '--- انتخاب کنید ---')] + [
            ('illiterate', 'بی‌سواد'),
            ( 'high_school', 'دیپلم'),
            ('associate', 'فوق دیپلم'), ('bachelor', 'لیسانس'),
            ('master', 'فوق لیسانس'), ('phd', 'دکترا'),
        ],
        required=False
    )
    mother_job = forms.CharField(
        label=_('شغل مادر'), max_length=150, required=False,
        widget=forms.TextInput(attrs={"placeholder": "شغل مادر"})
    )

    # ─── بیمه ─────────────────────────────────────────────────────
    insurance_status = forms.ChoiceField(
        label=_('وضعیت بیمه'),
        choices=Player.InsuranceStatus.choices,
        initial='none'
    )
    insurance_expiry_date = jDateField(
        label=_('تاریخ انقضای بیمه'),
        required=False,
        input_formats=['%Y/%m/%d', '%Y-%m-%d'],
        widget=forms.TextInput(attrs={"placeholder": "در صورت داشتن بیمه وارد کنید"})
    )

    # ─── تأیید شرایط ──────────────────────────────────────────────
    agree_terms = forms.BooleanField(
        label=_('قوانین و مقررات باشگاه را خوانده و قبول دارم'),
        error_messages={"required": "تأیید قوانین الزامی است."}
    )

    # ─── Validation ───────────────────────────────────────────────
    def clean_national_id(self):
        nid = self.cleaned_data["national_id"]
        if Player.objects.filter(national_id=nid).exists():
            raise forms.ValidationError("این کد ملی قبلاً ثبت شده است.")
        return nid

    def clean(self):
        cleaned = super().clean()
        ins_status = cleaned.get("insurance_status")
        ins_expiry = cleaned.get("insurance_expiry_date")
        if ins_status == "active" and not ins_expiry:
            self.add_error(
                "insurance_expiry_date",
                "در صورت داشتن بیمه فعال، تاریخ انقضا الزامی است."
            )
        return cleaned

    def clean_national_id_validate_checksum(self):
        """اعتبارسنجی الگوریتم کد ملی ایران."""
        nid = self.cleaned_data.get("national_id", "")
        if len(set(nid)) == 1:   # مثل 1111111111
            raise forms.ValidationError("کد ملی وارد شده معتبر نیست.")
        # الگوریتم کنترل کد ملی
        digits = [int(d) for d in nid]
        check  = digits[-1]
        total  = sum(digits[i] * (10 - i) for i in range(9))
        rem    = total % 11
        if not ((rem < 2 and check == rem) or (rem >= 2 and check == 11 - rem)):
            raise forms.ValidationError("کد ملی وارد شده معتبر نیست.")
        return nid


class TechnicalProfileForm(forms.ModelForm):
    """فرم ایجاد/ویرایش پروفایل فنی — فقط مربی و مدیر فنی."""

    class Meta:
        model  = TechnicalProfile
        fields = ["shirt_number", "position", "skill_level", "is_two_footed", "coach_notes"]
        widgets = {
            "coach_notes": forms.Textarea(attrs={"rows": 3}),
        }
        labels = {
            "shirt_number": "شماره پیراهن",
            "position":     "پست",
            "skill_level":  "سطح مهارت",
            "is_two_footed": "دوپا",
            "coach_notes":  "یادداشت مربی",
        }


class ExerciseUploadForm(forms.Form):
    """فرم آپلود تمرین توسط مربی."""
    title           = forms.CharField(label="عنوان تمرین", max_length=255)
    description     = forms.CharField(label="توضیحات", required=False, widget=forms.Textarea(attrs={"rows": 3}))
    media_type      = forms.ChoiceField(
        label="نوع فایل",
        choices=[("video","ویدیو"), ("image","تصویر"), ("gif","گیف"), ("document","سند")]
    )
    file            = forms.FileField(label="فایل تمرین")
    thumbnail       = forms.ImageField(label="تصویر بندانگشتی", required=False)
    duration_minutes = forms.IntegerField(label="مدت زمان (دقیقه)", required=False, min_value=1)
    is_public       = forms.BooleanField(label="قابل مشاهده برای همه مربیان", required=False)
    categories      = forms.MultipleChoiceField(
        label="دسته‌های مرتبط", required=False,
        widget=forms.CheckboxSelectMultiple
    )

    def __init__(self, *args, coach=None, **kwargs):
        super().__init__(*args, **kwargs)
        if coach:
            from ..models import TrainingCategory
            cats = TrainingCategory.objects.filter(
                coachcategoryrate__coach=coach, is_active=True
            )
            self.fields["categories"].choices = [(c.pk, c.name) for c in cats]
