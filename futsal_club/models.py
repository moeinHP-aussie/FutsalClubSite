"""
سیستم جامع مدیریت باشگاه فوتسال
Comprehensive Futsal Club Management System
models.py - Designed with Persian localization for Iranian users
"""

import uuid
from django.db import models
from django.contrib.auth.models import AbstractBaseUser, BaseUserManager, PermissionsMixin
from django.core.validators import RegexValidator, MinLengthValidator, MaxLengthValidator, MinValueValidator, MaxValueValidator
from django.utils.translation import gettext_lazy as _
from django.utils import timezone
from django_jalali.db import models as jmodels


# ─────────────────────────────────────────────
#  Validators
# ─────────────────────────────────────────────
phone_validator = RegexValidator(
    regex=r'^09\d{9}$',
    message=_('شماره موبایل باید ۱۱ رقم بوده و با ۰۹ شروع شود.')
)

national_id_validator = RegexValidator(
    regex=r'^\d{10}$',
    message=_('کد ملی باید دقیقاً ۱۰ رقم باشد.')
)


# ─────────────────────────────────────────────
#  Role Choices
# ─────────────────────────────────────────────
class Role(models.TextChoices):
    NEW_APPLICANT       = 'new_applicant',       _('متقاضی جدید')
    TECHNICAL_DIRECTOR  = 'technical_director',  _('مدیر فنی')
    FINANCE_MANAGER     = 'finance_manager',     _('مدیر مالی')
    COACH               = 'coach',               _('مربی')
    PLAYER              = 'player',              _('بازیکن')


# ─────────────────────────────────────────────
#  Custom User Manager
# ─────────────────────────────────────────────
class CustomUserManager(BaseUserManager):
    def create_user(self, username, password=None, **extra_fields):
        if not username:
            raise ValueError(_('نام کاربری الزامی است.'))
        user = self.model(username=username, **extra_fields)
        user.set_password(password)
        user.save(using=self._db)
        return user

    def create_superuser(self, username, password=None, **extra_fields):
        extra_fields.setdefault('is_staff', True)
        extra_fields.setdefault('is_superuser', True)
        return self.create_user(username, password, **extra_fields)


# ─────────────────────────────────────────────
#  Custom User (Multi-Role RBAC)
# ─────────────────────────────────────────────
class CustomUser(AbstractBaseUser, PermissionsMixin):
    """
    کاربر سفارشی با پشتیبانی از نقش‌های چندگانه.
    یک کاربر می‌تواند همزمان چندین نقش داشته باشد.
    """
    id          = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    username    = models.CharField(_('نام کاربری'), max_length=150, unique=True)
    email       = models.EmailField(_('ایمیل'), blank=True)
    first_name  = models.CharField(_('نام'), max_length=100)
    last_name   = models.CharField(_('نام خانوادگی'), max_length=100)
    phone       = models.CharField(_('شماره موبایل'), max_length=11, validators=[phone_validator], blank=True)
    avatar      = models.ImageField(_('تصویر پروفایل'), upload_to='avatars/', null=True, blank=True)

    # ── Multi-role booleans ──────────────────
    is_new_applicant      = models.BooleanField(_('متقاضی جدید'), default=False)
    is_technical_director = models.BooleanField(_('مدیر فنی'), default=False)
    is_finance_manager    = models.BooleanField(_('مدیر مالی'), default=False)
    is_coach              = models.BooleanField(_('مربی'), default=False)
    is_player             = models.BooleanField(_('بازیکن'), default=False)

    is_active   = models.BooleanField(_('فعال'), default=True)
    is_staff    = models.BooleanField(_('کارمند سیستم'), default=False)
    date_joined = jmodels.jDateTimeField(_('تاریخ عضویت'), default=timezone.now)

    objects = CustomUserManager()

    USERNAME_FIELD  = 'username'
    REQUIRED_FIELDS = ['first_name', 'last_name']

    class Meta:
        verbose_name        = _('کاربر')
        verbose_name_plural = _('کاربران')

    def __str__(self):
        return f'{self.first_name} {self.last_name} ({self.username})'

    def get_full_name(self):
        """سازگاری با Django AbstractUser"""
        name = f'{self.first_name} {self.last_name}'.strip()
        return name or self.username

    def get_short_name(self):
        return self.first_name or self.username

    def get_roles(self):
        roles = []
        if self.is_new_applicant:      roles.append(Role.NEW_APPLICANT)
        if self.is_technical_director: roles.append(Role.TECHNICAL_DIRECTOR)
        if self.is_finance_manager:    roles.append(Role.FINANCE_MANAGER)
        if self.is_coach:              roles.append(Role.COACH)
        if self.is_player:             roles.append(Role.PLAYER)
        return roles

    def has_role(self, role: str) -> bool:
        return role in self.get_roles()


# ─────────────────────────────────────────────
#  Education & Job Choices
# ─────────────────────────────────────────────
class EducationLevel(models.TextChoices):
    ILLITERATE      = 'illiterate',     _('بی‌سواد')
    ELEMENTARY      = 'elementary',     _('ابتدایی')
    MIDDLE_SCHOOL   = 'middle',         _('راهنمایی')
    HIGH_SCHOOL     = 'high_school',    _('دیپلم')
    ASSOCIATE       = 'associate',      _('فوق دیپلم')
    BACHELOR        = 'bachelor',       _('لیسانس')
    MASTER          = 'master',         _('فوق لیسانس')
    PHD             = 'phd',            _('دکترا')


# ─────────────────────────────────────────────
#  Player Model
# ─────────────────────────────────────────────
class Player(models.Model):
    """
    مدل بازیکن با تمامی اطلاعات شخصی، بیومتریک، بیمه و وضعیت ثبت‌نام.
    """

    class Status(models.TextChoices):
        PENDING  = 'pending',  _('در انتظار تأیید')
        APPROVED = 'approved', _('تأیید شده')
        REJECTED = 'rejected', _('رد شده')
        ARCHIVED = 'archived', _('آرشیو شده')

    class HandPreference(models.TextChoices):
        RIGHT = 'R', _('راست')
        LEFT  = 'L', _('چپ')

    class FootPreference(models.TextChoices):
        RIGHT = 'R', _('راست')
        LEFT  = 'L', _('چپ')

    class InsuranceStatus(models.TextChoices):
        NONE   = 'none',   _('بدون بیمه')
        ACTIVE = 'active', _('دارای بیمه فعال')

    # ── Identifiers ─────────────────────────
    player_id   = models.CharField(
        _('شناسه یکتا بازیکن'),
        max_length=12, unique=True, editable=False
    )
    user        = models.OneToOneField(
        CustomUser, on_delete=models.SET_NULL,
        null=True, blank=True,
        related_name='player_profile',
        verbose_name=_('حساب کاربری')
    )

    # ── Personal Info ────────────────────────
    first_name  = models.CharField(_('نام'), max_length=100)
    last_name   = models.CharField(_('نام خانوادگی'), max_length=100)
    father_name = models.CharField(_('نام پدر'), max_length=100)
    dob         = jmodels.jDateField(_('تاریخ تولد (شمسی)'))
    national_id = models.CharField(
        _('کد ملی'), max_length=10,
        unique=True, validators=[national_id_validator]
    )
    phone       = models.CharField(_('موبایل بازیکن'), max_length=11, validators=[phone_validator])
    father_phone = models.CharField(_('موبایل پدر'), max_length=11, validators=[phone_validator])
    mother_phone = models.CharField(_('موبایل مادر'), max_length=11, validators=[phone_validator], blank=True)
    address     = models.TextField(_('آدرس'), blank=True)

    # ── Biometrics ───────────────────────────
    height          = models.PositiveSmallIntegerField(_('قد (سانتی‌متر)'), null=True, blank=True)
    weight          = models.DecimalField(_('وزن (کیلوگرم)'), max_digits=5, decimal_places=1, null=True, blank=True)
    preferred_hand  = models.CharField(_('دست برتر'), max_length=1, choices=HandPreference.choices, default=HandPreference.RIGHT)
    preferred_foot  = models.CharField(_('پای برتر'), max_length=1, choices=FootPreference.choices, default=FootPreference.RIGHT)
    medical_history = models.TextField(_('سابقه پزشکی'), blank=True)
    injury_history  = models.TextField(_('سابقه آسیب‌دیدگی'), blank=True)

    # ── Family Background ────────────────────
    father_education = models.CharField(_('تحصیلات پدر'), max_length=20, choices=EducationLevel.choices, blank=True)
    father_job       = models.CharField(_('شغل پدر'), max_length=150, blank=True)
    mother_education = models.CharField(_('تحصیلات مادر'), max_length=20, choices=EducationLevel.choices, blank=True)
    mother_job       = models.CharField(_('شغل مادر'), max_length=150, blank=True)

    # ── Insurance ────────────────────────────
    insurance_status      = models.CharField(
        _('وضعیت بیمه'), max_length=10,
        choices=InsuranceStatus.choices, default=InsuranceStatus.NONE,
        help_text=_('در صورت نداشتن بیمه، از گزینه «بدون بیمه» استفاده کنید.')
    )
    insurance_expiry_date = jmodels.jDateField(_('تاریخ انقضای بیمه'), null=True, blank=True)
    insurance_image       = models.ImageField(
        _('تصویر بیمه‌نامه'), upload_to='insurance/',
        null=True, blank=True
    )

    # ── Workflow Status ──────────────────────
    status          = models.CharField(_('وضعیت'), max_length=10, choices=Status.choices, default=Status.PENDING)
    approved_by     = models.ForeignKey(
        CustomUser, on_delete=models.SET_NULL,
        null=True, blank=True,
        related_name='approved_players',
        verbose_name=_('تأیید شده توسط')
    )
    approval_date   = jmodels.jDateTimeField(_('تاریخ تأیید'), null=True, blank=True)
    registration_date = jmodels.jDateTimeField(_('تاریخ ثبت‌نام'), auto_now_add=True)
    notes           = models.TextField(_('یادداشت'), blank=True)

    # ── Soft Delete ──────────────────────────
    is_archived     = models.BooleanField(_('آرشیو شده'), default=False)
    archived_at     = jmodels.jDateTimeField(_('تاریخ آرشیو'), null=True, blank=True)
    archive_reason  = models.TextField(_('دلیل آرشیو'), blank=True)

    # ── Timestamps ───────────────────────────
    created_at  = jmodels.jDateTimeField(_('تاریخ ایجاد'), auto_now_add=True)
    updated_at  = jmodels.jDateTimeField(_('آخرین ویرایش'), auto_now=True)

    class Meta:
        verbose_name        = _('بازیکن')
        verbose_name_plural = _('بازیکنان')
        ordering            = ['last_name', 'first_name']

    def __str__(self):
        return f'{self.first_name} {self.last_name} ({self.player_id})'

    def save(self, *args, **kwargs):
        if not self.player_id:
            self.player_id = self._generate_player_id()
        super().save(*args, **kwargs)

    @classmethod
    def _generate_player_id(cls):
        """تولید شناسه یکتا برای بازیکن به فرمت PLY-XXXXXXXX — با مدیریت تداخل همزمان"""
        import random, string
        while True:
            suffix = ''.join(random.choices(string.digits, k=8))
            candidate = f'PLY-{suffix}'
            if not cls.objects.filter(player_id=candidate).exists():
                return candidate

    def archive(self, reason=''):
        """آرشیو نرم بازیکن به جای حذف"""
        self.is_archived    = True
        self.status         = self.Status.ARCHIVED
        self.archived_at    = timezone.now()
        self.archive_reason = reason
        self.save(update_fields=['is_archived', 'status', 'archived_at', 'archive_reason'])

    def get_age_on_reference(self):
        """
        سن بازیکن در تاریخ مرجع ۱۱ دی ماه سال جاری.
        این مقدار هر سال به‌صورت خودکار تغییر می‌کند.
        """
        try:
            from jdatetime import date as jdate
            today       = jdate.today()
            reference_g = jdate(today.year, 10, 11).togregorian()
            birth_g     = self.dob.togregorian()
            age = reference_g.year - birth_g.year
            if (birth_g.month, birth_g.day) > (reference_g.month, reference_g.day):
                age -= 1
            return age
        except Exception:
            return None

    def get_age_category(self):
        """
        رده سنی به فرمت «زیر X» — به‌صورت خودکار هر سال به‌روز می‌شود.
        مبنا: سن در ۱۱ دی ماه سال جاری.
        """
        age = self.get_age_on_reference()
        if age is None:
            return 'نامشخص'
        for limit in [8, 9, 10, 11, 12, 13, 14, 15, 16, 17, 18, 19, 20, 21, 22]:
            if age < limit:
                return 'زیر ' + str(limit)
        return 'بزرگسال'

    def is_insurance_expiring_soon(self, days=30):
        """آیا بیمه ظرف X روز آینده منقضی می‌شود؟"""
        if self.insurance_expiry_date and self.insurance_status == self.InsuranceStatus.ACTIVE:
            from jdatetime import date as jdate
            today       = jdate.today()
            expiry      = jdate(
                self.insurance_expiry_date.year,
                self.insurance_expiry_date.month,
                self.insurance_expiry_date.day
            )
            delta = (expiry.togregorian() - today.togregorian()).days
            return 0 <= delta <= days
        return False


# ─────────────────────────────────────────────
#  Soft Trait Type (Dynamic — defined by Technical Director)
# ─────────────────────────────────────────────
class SoftTraitType(models.Model):
    """
    انواع ویژگی‌های نرم که توسط مدیر فنی تعریف می‌شوند.
    مثال: رهبری، مهارت اجتماعی، روحیه تیمی
    """
    name        = models.CharField(_('نام ویژگی'), max_length=100, unique=True)
    description = models.TextField(_('توضیحات'), blank=True)
    is_active   = models.BooleanField(_('فعال'), default=True)
    created_by  = models.ForeignKey(
        CustomUser, on_delete=models.SET_NULL, null=True, blank=True,
        related_name='created_trait_types', verbose_name=_('ایجاد شده توسط')
    )
    created_at  = jmodels.jDateTimeField(_('تاریخ ایجاد'), auto_now_add=True)

    class Meta:
        verbose_name        = _('نوع ویژگی نرم')
        verbose_name_plural = _('انواع ویژگی نرم')

    def __str__(self):
        return self.name


# ─────────────────────────────────────────────
#  Technical Player Profile (Restricted)
# ─────────────────────────────────────────────
class TechnicalProfile(models.Model):
    """
    پروفایل فنی بازیکن — فقط قابل دسترس توسط مربی و مدیر فنی.
    """

    class Position(models.TextChoices):
        PIVOT   = 'pivot',  _('پیوت')
        WINGER  = 'winger', _('وینگر / بال')
        FIXO    = 'fixo',   _('فیکسو')
        GK      = 'gk',     _('دروازه‌بان')
        NONE    = '-',      _('مشخص نشده')

    class SkillLevel(models.TextChoices):
        A = 'A', 'A'
        B = 'B', 'B'
        C = 'C', 'C'
        D = 'D', 'D'
        E = 'E', 'E'
        F = 'F', 'F'

    player          = models.OneToOneField(
        Player, on_delete=models.CASCADE,
        related_name='technical_profile', verbose_name=_('بازیکن')
    )
    shirt_number    = models.PositiveSmallIntegerField(_('شماره پیراهن'), null=True, blank=True)
    position        = models.CharField(
        _('پست'), max_length=10,
        choices=Position.choices, default=Position.NONE
    )
    skill_level     = models.CharField(
        _('سطح مهارت'), max_length=1,
        choices=SkillLevel.choices, blank=True
    )
    is_two_footed   = models.BooleanField(_('دوپا'), default=False)
    coach_notes     = models.TextField(_('یادداشت مربی'), blank=True)
    updated_by      = models.ForeignKey(
        CustomUser, on_delete=models.SET_NULL, null=True, blank=True,
        related_name='updated_technical_profiles', verbose_name=_('آخرین ویرایش توسط')
    )
    updated_at      = jmodels.jDateTimeField(_('آخرین ویرایش'), auto_now=True)

    class Meta:
        verbose_name        = _('پروفایل فنی')
        verbose_name_plural = _('پروفایل‌های فنی')

    def __str__(self):
        return f'پروفایل فنی {self.player}'


class PlayerSoftTrait(models.Model):
    """
    امتیاز یک بازیکن در یک ویژگی نرم خاص (۱ تا ۱۰).
    """
    technical_profile = models.ForeignKey(
        TechnicalProfile, on_delete=models.CASCADE,
        related_name='soft_traits', verbose_name=_('پروفایل فنی')
    )
    trait_type  = models.ForeignKey(
        SoftTraitType, on_delete=models.CASCADE,
        related_name='player_traits', verbose_name=_('نوع ویژگی')
    )
    score       = models.PositiveSmallIntegerField(
        _('امتیاز'), default=5,
        validators=[MinValueValidator(1), MaxValueValidator(10)],
        help_text=_('بازه ۱ تا ۱۰')
    )
    note        = models.CharField(_('یادداشت'), max_length=255, blank=True)
    evaluated_by = models.ForeignKey(
        CustomUser, on_delete=models.SET_NULL, null=True, blank=True,
        verbose_name=_('ارزیابی شده توسط')
    )
    evaluated_at = jmodels.jDateTimeField(_('تاریخ ارزیابی'), auto_now=True)

    class Meta:
        verbose_name        = _('ویژگی نرم بازیکن')
        verbose_name_plural = _('ویژگی‌های نرم بازیکنان')
        unique_together     = ('technical_profile', 'trait_type')

    def __str__(self):
        return f'{self.technical_profile.player} — {self.trait_type}: {self.score}'


# ─────────────────────────────────────────────
#  Coach
# ─────────────────────────────────────────────
class Coach(models.Model):
    """
    مدل مربی با اطلاعات مالی و تخصصی.
    نرخ تدریس به ازای هر دسته آموزشی جداگانه تعریف می‌شود.
    """

    class Degree(models.TextChoices):
        LEVEL1 = 'level1', _('درجه ۱')
        LEVEL2 = 'level2', _('درجه ۲')
        LEVEL3 = 'level3', _('درجه ۳')
        AFC_A  = 'afc_a',  _('AFC A')
        AFC_B  = 'afc_b',  _('AFC B')
        AFC_C  = 'afc_c',  _('AFC C')
        OTHER  = 'other',  _('سایر')

    user            = models.OneToOneField(
        CustomUser, on_delete=models.CASCADE,
        related_name='coach_profile', verbose_name=_('حساب کاربری')
    )
    first_name      = models.CharField(_('نام'), max_length=100)
    last_name       = models.CharField(_('نام خانوادگی'), max_length=100)
    degree          = models.CharField(_('مدرک مربیگری'), max_length=10, choices=Degree.choices, blank=True)
    phone           = models.CharField(_('موبایل'), max_length=11, validators=[phone_validator])
    bank_card_number = models.CharField(
        _('شماره کارت بانکی'), max_length=16, blank=True,
        validators=[RegexValidator(r'^\d{16}$', _('شماره کارت باید ۱۶ رقم باشد.'))]
    )
    is_active       = models.BooleanField(_('فعال'), default=True)
    created_at      = jmodels.jDateTimeField(_('تاریخ ایجاد'), auto_now_add=True)

    class Meta:
        verbose_name        = _('مربی')
        verbose_name_plural = _('مربیان')

    def __str__(self):
        return f'{self.first_name} {self.last_name}'


# ─────────────────────────────────────────────
#  Training Category
# ─────────────────────────────────────────────
class TrainingCategory(models.Model):
    """
    دسته آموزشی (گروه تمرینی).
    روزها و ساعات تمرین به صورت رکوردهای جداگانه در TrainingSchedule ذخیره می‌شوند.
    """
    name        = models.CharField(_('نام دسته'), max_length=150, unique=True)
    description = models.TextField(_('توضیحات'), blank=True)
    coaches     = models.ManyToManyField(
        Coach, through='CoachCategoryRate',
        related_name='categories', verbose_name=_('مربیان')
    )
    players     = models.ManyToManyField(
        Player,
        related_name='categories',
        blank=True, verbose_name=_('بازیکنان')
    )
    monthly_fee = models.DecimalField(_('شهریه ماهانه (ریال)'), max_digits=12, decimal_places=0, default=0)
    is_active   = models.BooleanField(_('فعال'), default=True)
    created_at  = jmodels.jDateTimeField(_('تاریخ ایجاد'), auto_now_add=True)

    class Meta:
        verbose_name        = _('دسته آموزشی')
        verbose_name_plural = _('دسته‌های آموزشی')

    def __str__(self):
        return self.name


class TrainingSchedule(models.Model):
    """
    روز و ساعت تمرین یک دسته آموزشی.
    مثال: شنبه ساعت ۱۷
    """

    class Weekday(models.TextChoices):
        SATURDAY  = 'sat', _('شنبه')
        SUNDAY    = 'sun', _('یکشنبه')
        MONDAY    = 'mon', _('دوشنبه')
        TUESDAY   = 'tue', _('سه‌شنبه')
        WEDNESDAY = 'wed', _('چهارشنبه')
        THURSDAY  = 'thu', _('پنجشنبه')
        FRIDAY    = 'fri', _('جمعه')

    category    = models.ForeignKey(
        TrainingCategory, on_delete=models.CASCADE,
        related_name='schedules', verbose_name=_('دسته آموزشی')
    )
    weekday     = models.CharField(_('روز هفته'), max_length=3, choices=Weekday.choices)
    start_time  = models.TimeField(_('ساعت شروع'))
    end_time    = models.TimeField(_('ساعت پایان'), null=True, blank=True)
    location    = models.CharField(_('مکان / سالن'), max_length=200, blank=True)

    class Meta:
        verbose_name        = _('زمان‌بندی تمرین')
        verbose_name_plural = _('زمان‌بندی‌های تمرین')
        unique_together     = ('category', 'weekday', 'start_time')

    def __str__(self):
        return f'{self.category} — {self.get_weekday_display()} {self.start_time}'


class CoachCategoryRate(models.Model):
    """
    جدول واسط مربی–دسته آموزشی با نرخ تدریس اختصاصی.
    نرخ هر جلسه منحصر به مربی و دسته است.
    """
    coach       = models.ForeignKey(Coach, on_delete=models.CASCADE, verbose_name=_('مربی'))
    category    = models.ForeignKey(TrainingCategory, on_delete=models.CASCADE, verbose_name=_('دسته آموزشی'))
    session_rate = models.DecimalField(_('نرخ هر جلسه (ریال)'), max_digits=12, decimal_places=0)
    is_active   = models.BooleanField(_('فعال'), default=True)
    assigned_at = jmodels.jDateTimeField(_('تاریخ تخصیص'), auto_now_add=True)

    class Meta:
        verbose_name        = _('نرخ مربی در دسته')
        verbose_name_plural = _('نرخ‌های مربیان در دسته‌ها')
        unique_together     = ('coach', 'category')

    def __str__(self):
        return f'{self.coach} | {self.category} — {self.session_rate} ریال'


# ─────────────────────────────────────────────
#  Attendance
# ─────────────────────────────────────────────
class AttendanceSheet(models.Model):
    """
    ماتریس حضور و غیاب ماهانه برای یک دسته آموزشی.
    """
    category        = models.ForeignKey(
        TrainingCategory, on_delete=models.CASCADE,
        related_name='attendance_sheets', verbose_name=_('دسته آموزشی')
    )
    jalali_year     = models.PositiveSmallIntegerField(_('سال شمسی'))
    jalali_month    = models.PositiveSmallIntegerField(_('ماه شمسی'))
    is_finalized    = models.BooleanField(_('نهایی شده'), default=False)
    created_at      = jmodels.jDateTimeField(_('تاریخ ایجاد'), auto_now_add=True)
    finalized_at    = jmodels.jDateTimeField(_('تاریخ نهایی‌سازی'), null=True, blank=True)
    finalized_by    = models.ForeignKey(
        CustomUser, on_delete=models.SET_NULL, null=True, blank=True,
        related_name='finalized_sheets', verbose_name=_('نهایی شده توسط')
    )

    class Meta:
        verbose_name        = _('لیست حضور و غیاب')
        verbose_name_plural = _('لیست‌های حضور و غیاب')
        unique_together     = ('category', 'jalali_year', 'jalali_month')

    def __str__(self):
        return f'{self.category} — {self.jalali_year}/{self.jalali_month:02d}'


class SessionDate(models.Model):
    """یک جلسه تمرینی خاص در یک لیست حضور و غیاب."""
    sheet           = models.ForeignKey(
        AttendanceSheet, on_delete=models.CASCADE,
        related_name='session_dates', verbose_name=_('لیست')
    )
    date            = jmodels.jDateField(_('تاریخ جلسه'))
    session_number  = models.PositiveSmallIntegerField(_('شماره جلسه'))
    notes           = models.CharField(_('یادداشت'), max_length=255, blank=True)

    class Meta:
        verbose_name        = _('تاریخ جلسه')
        verbose_name_plural = _('تاریخ جلسات')
        unique_together     = ('sheet', 'date')
        ordering            = ['date']

    def __str__(self):
        return f'{self.sheet} — جلسه {self.session_number} ({self.date})'


class PlayerAttendance(models.Model):
    """رکورد حضور یک بازیکن در یک جلسه."""

    class AttendanceStatus(models.TextChoices):
        PRESENT = 'present', _('حاضر')
        ABSENT  = 'absent',  _('غایب')
        EXCUSED = 'excused', _('غیبت موجه')

    session     = models.ForeignKey(SessionDate, on_delete=models.CASCADE, related_name='player_records', verbose_name=_('جلسه'))
    player      = models.ForeignKey(Player, on_delete=models.CASCADE, related_name='attendances', verbose_name=_('بازیکن'))
    status      = models.CharField(_('وضعیت'), max_length=10, choices=AttendanceStatus.choices, default=AttendanceStatus.ABSENT)
    note        = models.CharField(_('یادداشت'), max_length=255, blank=True)

    class Meta:
        verbose_name        = _('حضور بازیکن')
        verbose_name_plural = _('حضور بازیکنان')
        unique_together     = ('session', 'player')

    def __str__(self):
        return f'{self.player} — {self.session}: {self.get_status_display()}'


class CoachAttendance(models.Model):
    """رکورد حضور یک مربی در یک جلسه."""

    class AttendanceStatus(models.TextChoices):
        PRESENT = 'present', _('حاضر')
        ABSENT  = 'absent',  _('غایب')
        EXCUSED = 'excused', _('غیبت موجه')

    session     = models.ForeignKey(SessionDate, on_delete=models.CASCADE, related_name='coach_records', verbose_name=_('جلسه'))
    coach       = models.ForeignKey(Coach, on_delete=models.CASCADE, related_name='attendances', verbose_name=_('مربی'))
    status      = models.CharField(_('وضعیت'), max_length=10, choices=AttendanceStatus.choices, default=AttendanceStatus.ABSENT)
    note        = models.CharField(_('یادداشت'), max_length=255, blank=True)

    class Meta:
        verbose_name        = _('حضور مربی')
        verbose_name_plural = _('حضور مربیان')
        unique_together     = ('session', 'coach')

    def __str__(self):
        return f'{self.coach} — {self.session}: {self.get_status_display()}'


# ─────────────────────────────────────────────
#  Financial Models
# ─────────────────────────────────────────────
class PlayerInvoice(models.Model):
    """
    فاکتور ماهانه شهریه بازیکن — تولید خودکار توسط مدیر مالی.
    """

    class PaymentStatus(models.TextChoices):
        PENDING         = 'pending',         _('در انتظار پرداخت')
        PAID            = 'paid',            _('پرداخت شده')
        DEBTOR          = 'debtor',          _('بدهکار')
        PENDING_CONFIRM = 'pending_confirm', _('در انتظار تأیید (رسید آپلود شده)')

    player          = models.ForeignKey(Player, on_delete=models.PROTECT, related_name='invoices', verbose_name=_('بازیکن'))
    category        = models.ForeignKey(TrainingCategory, on_delete=models.PROTECT, related_name='invoices', verbose_name=_('دسته آموزشی'))
    jalali_year     = models.PositiveSmallIntegerField(_('سال شمسی'))
    jalali_month    = models.PositiveSmallIntegerField(_('ماه شمسی'))
    amount          = models.DecimalField(_('مبلغ (ریال)'), max_digits=14, decimal_places=0)
    discount        = models.DecimalField(_('تخفیف (ریال)'), max_digits=12, decimal_places=0, default=0)
    final_amount    = models.DecimalField(_('مبلغ نهایی (ریال)'), max_digits=14, decimal_places=0)
    status          = models.CharField(_('وضعیت پرداخت'), max_length=20, choices=PaymentStatus.choices, default=PaymentStatus.PENDING)
    receipt_image   = models.ImageField(_('تصویر رسید'), upload_to='receipts/', null=True, blank=True)
    zarinpal_ref_id = models.CharField(_('شماره مرجع زرین‌پال'), max_length=100, blank=True)
    zarinpal_authority = models.CharField(_('Authority زرین‌پال'), max_length=100, blank=True)
    paid_at         = jmodels.jDateTimeField(_('تاریخ پرداخت'), null=True, blank=True)
    confirmed_by    = models.ForeignKey(
        CustomUser, on_delete=models.SET_NULL, null=True, blank=True,
        related_name='confirmed_invoices', verbose_name=_('تأیید شده توسط')
    )
    notes           = models.TextField(_('یادداشت'), blank=True)
    created_at      = jmodels.jDateTimeField(_('تاریخ صدور'), auto_now_add=True)
    updated_at      = jmodels.jDateTimeField(_('آخرین ویرایش'), auto_now=True)

    class Meta:
        verbose_name        = _('فاکتور شهریه')
        verbose_name_plural = _('فاکتورهای شهریه')
        unique_together     = ('player', 'category', 'jalali_year', 'jalali_month')
        ordering            = ['-jalali_year', '-jalali_month']

    def __str__(self):
        return f'فاکتور {self.player} — {self.jalali_year}/{self.jalali_month:02d}'

    def save(self, *args, **kwargs):
        # ✅ جلوگیری از منفی شدن مبلغ نهایی
        if self.discount > self.amount:
            raise ValueError(_('تخفیف نمی‌تواند از مبلغ اصلی بیشتر باشد.'))
        self.final_amount = self.amount - self.discount
        super().save(*args, **kwargs)


class CoachSalary(models.Model):
    """
    حقوق محاسبه‌شده مربی برای یک ماه در یک دسته آموزشی.
    """

    class SalaryStatus(models.TextChoices):
        CALCULATED = 'calculated', _('محاسبه شده')
        APPROVED   = 'approved',   _('تأیید شده')
        PAID       = 'paid',       _('پرداخت شده — منتظر تأیید مربی')
        CONFIRMED  = 'confirmed',  _('تأیید دریافت توسط مربی')

    coach           = models.ForeignKey(Coach, on_delete=models.PROTECT, related_name='salaries', verbose_name=_('مربی'))
    category        = models.ForeignKey(TrainingCategory, on_delete=models.PROTECT, related_name='coach_salaries', verbose_name=_('دسته آموزشی'))
    attendance_sheet = models.ForeignKey(AttendanceSheet, on_delete=models.PROTECT, related_name='coach_salaries', verbose_name=_('لیست حضور'))
    sessions_attended = models.PositiveSmallIntegerField(_('تعداد جلسات حاضر'), default=0)
    session_rate    = models.DecimalField(_('نرخ هر جلسه (ریال)'), max_digits=12, decimal_places=0)
    base_amount     = models.DecimalField(_('حقوق پایه (ریال)'), max_digits=14, decimal_places=0)
    manual_adjustment = models.DecimalField(_('تعدیل دستی (ریال)'), max_digits=12, decimal_places=0, default=0)
    adjustment_reason = models.CharField(_('دلیل تعدیل'), max_length=255, blank=True)
    final_amount    = models.DecimalField(_('حقوق نهایی (ریال)'), max_digits=14, decimal_places=0)
    status          = models.CharField(_('وضعیت'), max_length=15, choices=SalaryStatus.choices, default=SalaryStatus.CALCULATED)
    paid_at         = jmodels.jDateTimeField(_('تاریخ پرداخت'), null=True, blank=True)
    bank_receipt    = models.ImageField(
        _('تصویر فیش بانکی'), upload_to='salary_receipts/%Y/%m/', null=True, blank=True
    )
    coach_confirmed    = models.BooleanField(_('تأیید مربی'), default=False)
    coach_confirmed_at = jmodels.jDateTimeField(_('تاریخ تأیید مربی'), null=True, blank=True)
    processed_by    = models.ForeignKey(
        CustomUser, on_delete=models.SET_NULL, null=True, blank=True,
        related_name='processed_salaries', verbose_name=_('پردازش شده توسط')
    )
    created_at      = jmodels.jDateTimeField(_('تاریخ ایجاد'), auto_now_add=True)

    class Meta:
        verbose_name        = _('حقوق مربی')
        verbose_name_plural = _('حقوق مربیان')
        unique_together     = ('coach', 'category', 'attendance_sheet')

    def __str__(self):
        return f'حقوق {self.coach} | {self.category} — {self.attendance_sheet}'

    def save(self, *args, **kwargs):
        self.base_amount  = self.sessions_attended * self.session_rate
        self.final_amount = self.base_amount + self.manual_adjustment
        super().save(*args, **kwargs)


# ─────────────────────────────────────────────
#  Expense Tracking (Custom Fields)
# ─────────────────────────────────────────────
class ExpenseCategory(models.Model):
    """
    دسته‌بندی هزینه — قابل تعریف توسط مدیر مالی.
    مثال: اجاره سالن، تجهیزات، حمل‌ونقل
    """
    name        = models.CharField(_('نام دسته هزینه'), max_length=150, unique=True)
    description = models.TextField(_('توضیحات'), blank=True)
    is_active   = models.BooleanField(_('فعال'), default=True)
    created_by  = models.ForeignKey(
        CustomUser, on_delete=models.SET_NULL, null=True, blank=True,
        related_name='expense_categories', verbose_name=_('ایجاد شده توسط')
    )
    created_at  = jmodels.jDateTimeField(_('تاریخ ایجاد'), auto_now_add=True)

    class Meta:
        verbose_name        = _('دسته هزینه')
        verbose_name_plural = _('دسته‌های هزینه')

    def __str__(self):
        return self.name


class Expense(models.Model):
    """رکورد یک تراکنش هزینه."""

    class TransactionType(models.TextChoices):
        EXPENSE = 'expense', _('هزینه')
        INCOME  = 'income',  _('درآمد')

    category        = models.ForeignKey(ExpenseCategory, on_delete=models.PROTECT, related_name='transactions', verbose_name=_('دسته'))
    title           = models.CharField(_('عنوان'), max_length=255)
    amount          = models.DecimalField(_('مبلغ (ریال)'), max_digits=14, decimal_places=0)
    transaction_type = models.CharField(_('نوع تراکنش'), max_length=10, choices=TransactionType.choices, default=TransactionType.EXPENSE)
    date            = jmodels.jDateField(_('تاریخ'))
    description     = models.TextField(_('شرح'), blank=True)
    attachment      = models.FileField(_('پیوست'), upload_to='expenses/', null=True, blank=True)
    receipt_image   = models.ImageField(_('تصویر رسید'), upload_to='expense_receipts/%Y/%m/', null=True, blank=True)
    recorded_by     = models.ForeignKey(
        CustomUser, on_delete=models.SET_NULL, null=True, blank=True,
        related_name='recorded_expenses', verbose_name=_('ثبت شده توسط')
    )
    created_at      = jmodels.jDateTimeField(_('تاریخ ثبت'), auto_now_add=True)

    class Meta:
        verbose_name        = _('تراکنش مالی')
        verbose_name_plural = _('تراکنش‌های مالی')
        ordering            = ['-date']

    def __str__(self):
        return f'{self.title} — {self.amount} ریال ({self.date})'


# ─────────────────────────────────────────────
#  Announcements & Notifications
# ─────────────────────────────────────────────
class Announcement(models.Model):
    """
    اطلاعیه — ارسال توسط مربی یا مدیر فنی به دسته‌های آموزشی.
    """
    title       = models.CharField(_('عنوان'), max_length=255)
    body        = models.TextField(_('متن اطلاعیه'))
    author      = models.ForeignKey(
        CustomUser, on_delete=models.SET_NULL, null=True,
        related_name='announcements', verbose_name=_('نویسنده')
    )
    categories  = models.ManyToManyField(
        TrainingCategory, related_name='announcements',
        blank=True, verbose_name=_('دسته‌های هدف')
    )
    is_pinned   = models.BooleanField(_('سنجاق شده'), default=False)
    published_at = jmodels.jDateTimeField(_('تاریخ انتشار'), auto_now_add=True)

    class Meta:
        verbose_name        = _('اطلاعیه')
        verbose_name_plural = _('اطلاعیه‌ها')
        ordering            = ['-published_at']

    def __str__(self):
        return self.title


class Notification(models.Model):
    """
    اعلان سیستمی برای کاربران.
    مثال: هشدار انقضای بیمه
    """

    class NotificationType(models.TextChoices):
        INSURANCE_EXPIRY = 'insurance_expiry', _('انقضای بیمه')
        INVOICE_DUE      = 'invoice_due',      _('سررسید فاکتور')
        INVOICE_ISSUED   = 'invoice_issued',   _('صدور فاکتور شهریه')
        INVOICE_PAID     = 'invoice_paid',     _('تأیید پرداخت شهریه')
        SALARY_READY     = 'salary_ready',     _('آماده بودن حقوق')
        SALARY_PAID      = 'salary_paid',      _('پرداخت حقوق مربی')
        STAFF_INVOICE    = 'staff_invoice',    _('فاکتور دستی')
        PAYMENT_REMINDER = 'payment_reminder', _('یادآوری پرداخت شهریه')
        RECEIPT_UPLOADED = 'receipt_uploaded', _('رسید پرداخت آپلود شد')
        PLAYER_CHANGE    = 'player_change',    _('تغییر اطلاعات بازیکن')
        GENERAL          = 'general',          _('عمومی')

    recipient   = models.ForeignKey(
        CustomUser, on_delete=models.CASCADE,
        related_name='notifications', verbose_name=_('دریافت‌کننده')
    )
    type        = models.CharField(_('نوع اعلان'), max_length=30, choices=NotificationType.choices, default=NotificationType.GENERAL)
    title       = models.CharField(_('عنوان'), max_length=255)
    message     = models.TextField(_('پیام'))
    is_read     = models.BooleanField(_('خوانده شده'), default=False)
    related_player = models.ForeignKey(
        Player, on_delete=models.SET_NULL, null=True, blank=True,
        related_name='notifications', verbose_name=_('بازیکن مرتبط')
    )
    created_at  = jmodels.jDateTimeField(_('تاریخ ارسال'), auto_now_add=True)
    read_at     = jmodels.jDateTimeField(_('تاریخ خواندن'), null=True, blank=True)

    class Meta:
        verbose_name        = _('اعلان')
        verbose_name_plural = _('اعلان‌ها')
        ordering            = ['-created_at']

    def __str__(self):
        return f'{self.recipient} — {self.title}'

    def mark_as_read(self):
        self.is_read = True
        self.read_at = timezone.now()
        self.save(update_fields=['is_read', 'read_at'])


# ─────────────────────────────────────────────
#  Player Change Log
# ─────────────────────────────────────────────
class PlayerChangeLog(models.Model):
    """
    ثبت تغییرات روی اطلاعات بازیکن برای نمایش در داشبورد.
    """
    class ChangeType(models.TextChoices):
        PROFILE     = 'profile',     _('ویرایش اطلاعات شخصی')
        INSURANCE   = 'insurance',   _('بروزرسانی بیمه')
        TECH        = 'tech',        _('ویرایش پروفایل فنی')
        SOFT_TRAITS = 'soft_traits', _('ویرایش ویژگی نرم')
        ARCHIVE     = 'archive',     _('بایگانی')
        RESTORE     = 'restore',     _('بازگردانی')

    player      = models.ForeignKey(
        Player, on_delete=models.CASCADE,
        related_name='change_logs', verbose_name=_('بازیکن')
    )
    changed_by  = models.ForeignKey(
        CustomUser, on_delete=models.SET_NULL, null=True,
        related_name='player_changes', verbose_name=_('توسط')
    )
    change_type = models.CharField(_('نوع تغییر'), max_length=20, choices=ChangeType.choices)
    description = models.TextField(_('توضیح'), blank=True)
    created_at  = jmodels.jDateTimeField(_('زمان'), auto_now_add=True)

    class Meta:
        verbose_name        = _('تغییر بازیکن')
        verbose_name_plural = _('تغییرات بازیکنان')
        ordering            = ['-created_at']

    def __str__(self):
        return f'{self.player} — {self.get_change_type_display()}'


# ─────────────────────────────────────────────
#  Exercise Repository
# ─────────────────────────────────────────────
class ExerciseTag(models.Model):
    name = models.CharField(_('برچسب'), max_length=80, unique=True)

    class Meta:
        verbose_name        = _('برچسب تمرین')
        verbose_name_plural = _('برچسب‌های تمرین')

    def __str__(self):
        return self.name


class Exercise(models.Model):
    """
    مخزن تمرین — مربیان می‌توانند فایل‌های تمرینی آپلود کنند.
    مدیر فنی دسترسی مشاهده و دانلود همه تمرین‌ها را دارد.
    """

    class MediaType(models.TextChoices):
        VIDEO   = 'video',   _('ویدیو')
        IMAGE   = 'image',   _('تصویر')
        GIF     = 'gif',     _('گیف')
        DOCUMENT = 'document', _('سند')

    title       = models.CharField(_('عنوان تمرین'), max_length=255)
    description = models.TextField(_('توضیحات'), blank=True)
    media_type  = models.CharField(_('نوع رسانه'), max_length=10, choices=MediaType.choices)
    file        = models.FileField(_('فایل'), upload_to='exercises/')
    thumbnail   = models.ImageField(_('تصویر بندانگشتی'), upload_to='exercises/thumbnails/', null=True, blank=True)
    uploaded_by = models.ForeignKey(
        Coach, on_delete=models.SET_NULL, null=True, blank=True,
        related_name='exercises', verbose_name=_('آپلود شده توسط')
    )
    categories  = models.ManyToManyField(
        TrainingCategory, related_name='exercises',
        blank=True, verbose_name=_('دسته‌های مرتبط')
    )
    tags        = models.ManyToManyField(ExerciseTag, blank=True, verbose_name=_('برچسب‌ها'))
    duration_minutes = models.PositiveSmallIntegerField(_('مدت زمان (دقیقه)'), null=True, blank=True)
    is_public   = models.BooleanField(_('قابل مشاهده برای همه مربیان'), default=False)
    created_at  = jmodels.jDateTimeField(_('تاریخ آپلود'), auto_now_add=True)
    updated_at  = jmodels.jDateTimeField(_('آخرین ویرایش'), auto_now=True)

    class Meta:
        verbose_name        = _('تمرین')
        verbose_name_plural = _('تمرین‌ها')
        ordering            = ['-created_at']

    def __str__(self):
        return self.title


# ─────────────────────────────────────────────
#  Zarinpal Payment Log
# ─────────────────────────────────────────────
class PaymentLog(models.Model):
    """
    لاگ تراکنش‌های زرین‌پال برای پیگیری وضعیت پرداخت.
    """

    class PaymentResult(models.TextChoices):
        INITIATED = 'initiated', _('شروع شده')
        SUCCESS   = 'success',   _('موفق')
        FAILED    = 'failed',    _('ناموفق')
        CANCELED  = 'canceled',  _('لغو شده')

    invoice         = models.ForeignKey(
        PlayerInvoice, on_delete=models.PROTECT,
        related_name='payment_logs', verbose_name=_('فاکتور')
    )
    authority       = models.CharField(_('Authority'), max_length=100, unique=True)
    ref_id          = models.CharField(_('Ref ID'), max_length=100, blank=True)
    amount          = models.DecimalField(_('مبلغ (ریال)'), max_digits=14, decimal_places=0)
    result          = models.CharField(_('نتیجه'), max_length=15, choices=PaymentResult.choices, default=PaymentResult.INITIATED)
    ip_address      = models.GenericIPAddressField(_('آدرس IP'), null=True, blank=True)
    created_at      = jmodels.jDateTimeField(_('تاریخ ایجاد'), auto_now_add=True)
    verified_at     = jmodels.jDateTimeField(_('تاریخ تأیید'), null=True, blank=True)
    raw_response    = models.JSONField(_('پاسخ خام'), default=dict, blank=True)

    class Meta:
        verbose_name        = _('لاگ پرداخت')
        verbose_name_plural = _('لاگ‌های پرداخت')
        ordering            = ['-created_at']

    def __str__(self):
        return f'{self.invoice} — {self.authority} ({self.get_result_display()})'


# ─────────────────────────────────────────────
#  Player Activity Log (فید تغییرات)
# ─────────────────────────────────────────────
class PlayerActivityLog(models.Model):
    """
    ثبت خودکار تمام تغییرات مرتبط به بازیکن.
    برای نمایش در داشبورد مربی/مدیر فنی.
    """

    class ActionType(models.TextChoices):
        INSURANCE_UPDATED  = 'insurance_updated',  _('بروزرسانی بیمه')
        PROFILE_UPDATED    = 'profile_updated',    _('ویرایش اطلاعات')
        TECH_UPDATED       = 'tech_updated',       _('ویرایش پروفایل فنی')
        TRAITS_UPDATED     = 'traits_updated',     _('ویرایش ویژگی‌های نرم')
        CATEGORY_CHANGED   = 'category_changed',   _('تغییر دسته')
        ARCHIVED           = 'archived',           _('بایگانی')
        RESTORED           = 'restored',           _('بازگردانی')
        APPROVED           = 'approved',           _('تأیید ثبت‌نام')

    player     = models.ForeignKey(
        Player, on_delete=models.CASCADE,
        related_name='activity_logs', verbose_name=_('بازیکن')
    )
    actor      = models.ForeignKey(
        CustomUser, on_delete=models.SET_NULL, null=True, blank=True,
        related_name='player_actions', verbose_name=_('انجام‌دهنده')
    )
    action     = models.CharField(
        _('نوع عملیات'), max_length=30, choices=ActionType.choices
    )
    detail     = models.CharField(_('جزئیات'), max_length=500, blank=True)
    created_at = jmodels.jDateTimeField(_('زمان'), auto_now_add=True)

    class Meta:
        verbose_name        = _('لاگ فعالیت بازیکن')
        verbose_name_plural = _('لاگ‌های فعالیت بازیکنان')
        ordering            = ['-created_at']

    def __str__(self):
        return f'{self.player} — {self.get_action_display()} توسط {self.actor}'


# ─────────────────────────────────────────────
#  StaffInvoice — فاکتور دستی برای اعضاء باشگاه
# ─────────────────────────────────────────────
class StaffInvoice(models.Model):
    """
    فاکتور دستی که مدیر مالی برای هر کاربر سیستم صادر می‌کند.
    مثال: حق عضویت سالانه مربی، هزینه خاص برای مدیر فنی و...
    پرداخت از طریق درگاه زرین‌پال یا تأیید دستی.
    """

    class PaymentStatus(models.TextChoices):
        PENDING   = 'pending',   _('در انتظار پرداخت')
        PAID      = 'paid',      _('پرداخت شده — منتظر تأیید گیرنده')
        CONFIRMED = 'confirmed', _('تأیید دریافت توسط گیرنده')
        CANCELED  = 'canceled',  _('لغو شده')

    recipient       = models.ForeignKey(
        CustomUser, on_delete=models.PROTECT,
        related_name='staff_invoices', verbose_name=_('دریافت‌کننده')
    )
    title           = models.CharField(_('عنوان فاکتور'), max_length=255)
    description     = models.TextField(_('شرح'), blank=True)
    amount          = models.DecimalField(_('مبلغ (ریال)'), max_digits=14, decimal_places=0)
    status          = models.CharField(
        _('وضعیت'), max_length=15,
        choices=PaymentStatus.choices, default=PaymentStatus.PENDING
    )
    zarinpal_ref_id     = models.CharField(_('شماره مرجع'), max_length=100, blank=True)
    zarinpal_authority  = models.CharField(_('Authority'), max_length=100, blank=True)
    paid_at         = jmodels.jDateTimeField(_('تاریخ پرداخت'), null=True, blank=True)
    bank_receipt    = models.ImageField(
        _('تصویر فیش بانکی'), upload_to='staff_receipts/%Y/%m/', null=True, blank=True
    )
    recipient_confirmed    = models.BooleanField(_('تأیید گیرنده'), default=False)
    recipient_confirmed_at = jmodels.jDateTimeField(_('تاریخ تأیید گیرنده'), null=True, blank=True)
    created_by      = models.ForeignKey(
        CustomUser, on_delete=models.SET_NULL, null=True,
        related_name='issued_staff_invoices', verbose_name=_('صادرکننده')
    )
    created_at      = jmodels.jDateTimeField(_('تاریخ صدور'), auto_now_add=True)

    class Meta:
        verbose_name        = _('فاکتور دستی')
        verbose_name_plural = _('فاکتورهای دستی')
        ordering            = ['-created_at']

    def __str__(self):
        return f'{self.title} — {self.recipient} ({self.get_status_display()})'


# ─────────────────────────────────────────────
#  FinancialTransaction — تاریخچه مالی یکپارچه
# ─────────────────────────────────────────────
class FinancialTransaction(models.Model):
    """
    تاریخچه مالی یکپارچه برای همه کاربران سیستم.
    هر رویداد مالی (پرداخت شهریه، دریافت حقوق، صدور فاکتور) اینجا ثبت می‌شه.
    """

    class TxType(models.TextChoices):
        INVOICE_ISSUED    = 'invoice_issued',    _('صدور فاکتور شهریه')
        INVOICE_PAID      = 'invoice_paid',      _('پرداخت شهریه')
        SALARY_CALCULATED = 'salary_calculated', _('محاسبه حقوق')
        SALARY_PAID       = 'salary_paid',       _('پرداخت حقوق')
        STAFF_INVOICE     = 'staff_invoice',     _('فاکتور دستی')
        STAFF_INVOICE_PAID= 'staff_invoice_paid',_('پرداخت فاکتور دستی')
        EXPENSE           = 'expense',           _('ثبت هزینه')
        INCOME            = 'income',            _('ثبت درآمد')

    class Direction(models.TextChoices):
        CREDIT = 'credit', _('بستانکار')   # دریافت پول
        DEBIT  = 'debit',  _('بدهکار')    # پرداخت پول

    user            = models.ForeignKey(
        CustomUser, on_delete=models.CASCADE,
        related_name='financial_history', verbose_name=_('کاربر')
    )
    tx_type         = models.CharField(_('نوع'), max_length=30, choices=TxType.choices)
    direction       = models.CharField(_('جهت'), max_length=10, choices=Direction.choices)
    amount          = models.DecimalField(_('مبلغ (ریال)'), max_digits=14, decimal_places=0)
    description     = models.CharField(_('شرح'), max_length=500)
    # لینک‌های اختیاری به مدل‌های مرتبط
    player_invoice  = models.ForeignKey(
        PlayerInvoice, on_delete=models.SET_NULL, null=True, blank=True,
        related_name='transactions', verbose_name=_('فاکتور شهریه')
    )
    coach_salary    = models.ForeignKey(
        CoachSalary, on_delete=models.SET_NULL, null=True, blank=True,
        related_name='transactions', verbose_name=_('حقوق مربی')
    )
    staff_invoice   = models.ForeignKey(
        StaffInvoice, on_delete=models.SET_NULL, null=True, blank=True,
        related_name='transactions', verbose_name=_('فاکتور دستی')
    )
    performed_by    = models.ForeignKey(
        CustomUser, on_delete=models.SET_NULL, null=True, blank=True,
        related_name='performed_transactions', verbose_name=_('انجام‌دهنده')
    )
    created_at      = jmodels.jDateTimeField(_('تاریخ'), auto_now_add=True)

    class Meta:
        verbose_name        = _('تراکنش مالی')
        verbose_name_plural = _('تراکنش‌های مالی')
        ordering            = ['-created_at']

    def __str__(self):
        return f'{self.user} — {self.get_tx_type_display()} — {self.amount:,} ریال'