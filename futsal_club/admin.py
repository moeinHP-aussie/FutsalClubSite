"""
admin.py  —  UPDATED (Soft-Delete Aware + All Features)
─────────────────────────────────────────────────────────────────────
تمام تنظیمات پنل مدیریت با پشتیبانی از آرشیو نرم.
آرشیوشده‌ها پیش‌فرض پنهان هستند؛ فیلتر جداگانه‌ای برای مشاهده آن‌ها وجود دارد.
"""

from django.contrib import admin
from django.contrib.auth.admin import UserAdmin
from django.utils import timezone
from django.utils.html import format_html
from django.utils.translation import gettext_lazy as _
from django_jalali.admin.filters import JDateFieldListFilter

from .models import (
    AttendanceSheet, Coach, CoachAttendance, CoachCategoryRate,
    CoachSalary, CustomUser, Exercise, ExerciseTag, Expense,
    ExpenseCategory, Notification, Announcement,
    PaymentLog, Player, PlayerAttendance, PlayerInvoice,
    PlayerSoftTrait, SessionDate, SoftTraitType,
    TechnicalProfile, TrainingCategory, TrainingSchedule,
)

# ── Site branding ────────────────────────────────────────────────────
admin.site.site_header  = _("سیستم جامع مدیریت باشگاه فوتسال اسپاد")
admin.site.site_title   = _("پنل مدیریت")
admin.site.index_title  = _("خانه")


# ════════════════════════════════════════════════════════════════════
#  ACTIVE-ONLY Manager  (هم در admin و هم در code قابل استفاده)
# ════════════════════════════════════════════════════════════════════

class ActivePlayerFilter(admin.SimpleListFilter):
    """
    فیلتر نمایش وضعیت آرشیو در admin.
    پیش‌فرض: فقط بازیکنان فعال (is_archived=False).
    """
    title        = _("وضعیت آرشیو")
    parameter_name = "archived"

    def lookups(self, request, model_admin):
        return [
            ("active",   _("فعال")),
            ("archived", _("آرشیو‌شده")),
            ("all",      _("همه")),
        ]

    def queryset(self, request, queryset):
        val = self.value()
        if val == "archived":  return queryset.filter(is_archived=True)
        if val == "all":       return queryset
        return queryset.filter(is_archived=False)   # پیش‌فرض

    def choices(self, changelist):
        # اطمینان از اینکه "فعال" پیش‌فرض انتخاب‌شده باشد
        yield {
            "selected":   self.value() in (None, "active"),
            "query_string": changelist.get_query_string({self.parameter_name: "active"}),
            "display":    _("فعال"),
        }
        for lookup, title in self.lookup_choices:
            if lookup == "active":
                continue
            yield {
                "selected":   self.value() == lookup,
                "query_string": changelist.get_query_string({self.parameter_name: lookup}),
                "display":    title,
            }


# ════════════════════════════════════════════════════════════════════
#  CustomUser Admin
# ════════════════════════════════════════════════════════════════════

@admin.register(CustomUser)
class CustomUserAdmin(UserAdmin):
    list_display    = ("username", "full_name", "phone", "role_badges", "is_active")
    list_filter     = ("is_active", "is_staff", "is_player", "is_coach",
                       "is_technical_director", "is_finance_manager")
    search_fields   = ("username", "first_name", "last_name", "phone", "email")
    ordering        = ("last_name",)

    fieldsets = (
        (_("اطلاعات ورود"),  {"fields": ("username", "password")}),
        (_("اطلاعات شخصی"),  {"fields": ("first_name", "last_name", "email", "phone", "avatar")}),
        (_("نقش‌ها"),         {"fields": ("is_new_applicant", "is_technical_director",
                                          "is_finance_manager", "is_coach", "is_player")}),
        (_("دسترسی‌ها"),      {"fields": ("is_active", "is_staff", "is_superuser",
                                          "groups", "user_permissions")}),
        (_("تاریخ‌ها"),       {"fields": ("date_joined", "last_login")}),
    )
    add_fieldsets = (
        (None, {"classes": ("wide",), "fields": (
            "username", "first_name", "last_name", "phone", "password1", "password2",
        )}),
    )

    def full_name(self, obj):
        return f"{obj.first_name} {obj.last_name}"
    full_name.short_description = _("نام کامل")

    def role_badges(self, obj):
        color_map = {
            "new_applicant":      "#6c757d",
            "technical_director": "#007bff",
            "finance_manager":    "#28a745",
            "coach":              "#fd7e14",
            "player":             "#6f42c1",
        }
        label_map = {
            "new_applicant":      "متقاضی",
            "technical_director": "مدیر فنی",
            "finance_manager":    "مدیر مالی",
            "coach":              "مربی",
            "player":             "بازیکن",
        }
        badges = "".join(
            f'<span style="background:{color_map.get(r,"#999")};color:#fff;'
            f'padding:2px 7px;border-radius:4px;margin:1px;font-size:11px">'
            f'{label_map.get(r, r)}</span>'
            for r in obj.get_roles()
        )
        return format_html(badges or "—")
    role_badges.short_description = _("نقش‌ها")


# ════════════════════════════════════════════════════════════════════
#  Player Admin  —  Soft-Delete Aware
# ════════════════════════════════════════════════════════════════════

class TechnicalProfileInline(admin.StackedInline):
    model           = TechnicalProfile
    can_delete      = False
    extra           = 0
    fields          = ("shirt_number", "position", "skill_level", "is_two_footed", "coach_notes")
    verbose_name    = _("پروفایل فنی")


@admin.register(Player)
class PlayerAdmin(admin.ModelAdmin):
    list_display    = (
        "player_id", "full_name", "national_id", "phone",
        "status_badge", "insurance_badge", "age_category_display",
        "archived_badge",
    )
    list_filter     = (
        ActivePlayerFilter,          # ← فیلتر اصلی آرشیو
        "status",
        "insurance_status",
        ("dob", JDateFieldListFilter),
        ("registration_date", JDateFieldListFilter),
    )
    search_fields   = (
        "first_name", "last_name", "national_id",
        "player_id", "phone", "father_name",
    )
    readonly_fields = (
        "player_id", "registration_date",
        "age_category_display", "approved_by",
        "approval_date", "archived_at",
    )
    inlines         = [TechnicalProfileInline]
    list_per_page   = 30
    save_on_top     = True

    fieldsets = (
        (_("شناسه‌ها"),          {"fields": ("player_id", "user", "status", "approved_by", "approval_date")}),
        (_("اطلاعات شخصی"),     {"fields": ("first_name", "last_name", "father_name", "national_id",
                                             "dob", "age_category_display",
                                             "phone", "father_phone", "mother_phone", "address")}),
        (_("بیومتریک"),         {"fields": ("height", "weight", "preferred_hand", "preferred_foot"),
                                  "classes": ("collapse",)}),
        (_("سوابق سلامتی"),     {"fields": ("medical_history", "injury_history"),
                                  "classes": ("collapse",)}),
        (_("اطلاعات خانواده"),  {"fields": ("father_education", "father_job", "mother_education", "mother_job"),
                                  "classes": ("collapse",)}),
        (_("بیمه"),             {"fields": ("insurance_status", "insurance_expiry_date", "insurance_image")}),
        (_("آرشیو"),            {"fields": ("is_archived", "archived_at", "archive_reason"),
                                  "classes": ("collapse",)}),
        (_("یادداشت"),         {"fields": ("notes",)}),
    )

    actions = ["approve_selected", "archive_selected", "restore_selected"]

    # ── Default queryset: ACTIVE only ────────────────────────────
    def get_queryset(self, request):
        qs = super().get_queryset(request)
        # اگر فیلتر archived=archived یا all انتخاب شده باشد، رعایت می‌شود
        archived_param = request.GET.get("archived")
        if archived_param == "archived":
            return qs.filter(is_archived=True)
        if archived_param == "all":
            return qs
        return qs.filter(is_archived=False)  # پیش‌فرض

    # ── Display methods ───────────────────────────────────────────
    def full_name(self, obj):
        return f"{obj.first_name} {obj.last_name}"
    full_name.short_description = _("نام")

    def status_badge(self, obj):
        colors = {"pending": "#ffc107", "approved": "#28a745",
                  "rejected": "#dc3545", "archived": "#6c757d"}
        labels = {"pending": "در انتظار", "approved": "تأیید",
                  "rejected": "رد", "archived": "آرشیو"}
        return format_html(
            '<span style="background:{};color:#fff;padding:2px 8px;border-radius:4px">{}</span>',
            colors.get(obj.status, "#999"), labels.get(obj.status, obj.status)
        )
    status_badge.short_description = _("وضعیت")

    def insurance_badge(self, obj):
        if obj.insurance_status == "active":
            if obj.is_insurance_expiring_soon(7):
                return format_html('<span style="color:#e67e22">🚨 در حال انقضا</span>')
            if obj.is_insurance_expiring_soon(30):
                return format_html('<span style="color:#f39c12">⚠️ نزدیک انقضا</span>')
            return format_html('<span style="color:#27ae60">✔ فعال</span>')
        return format_html('<span style="color:#e74c3c">✘ ندارد</span>')
    insurance_badge.short_description = _("بیمه")

    def age_category_display(self, obj):
        return obj.get_age_category()
    age_category_display.short_description = _("رده سنی")

    def archived_badge(self, obj):
        if obj.is_archived:
            return format_html('<span style="color:#e74c3c;font-weight:bold">🗄 آرشیو</span>')
        return format_html('<span style="color:#27ae60">✓ فعال</span>')
    archived_badge.short_description = _("آرشیو")

    # ── Actions ──────────────────────────────────────────────────
    def approve_selected(self, request, queryset):
        count = 0
        for player in queryset.filter(status="pending", is_archived=False):
            player.status        = Player.Status.APPROVED
            player.approved_by   = request.user
            player.approval_date = timezone.now()
            player.save(update_fields=["status", "approved_by", "approval_date"])
            if player.user:
                player.user.is_player        = True
                player.user.is_new_applicant = False
                player.user.save(update_fields=["is_player", "is_new_applicant"])
            count += 1
        self.message_user(request, f"{count} بازیکن تأیید شد.")
    approve_selected.short_description = _("✅ تأیید بازیکنان انتخاب‌شده")

    def archive_selected(self, request, queryset):
        count = 0
        for player in queryset.filter(is_archived=False):
            player.archive(reason="آرشیو دسته‌جمعی از پنل مدیریت")
            if player.user:
                player.user.is_active = False
                player.user.save(update_fields=["is_active"])
            count += 1
        self.message_user(request, f"{count} بازیکن آرشیو شد.")
    archive_selected.short_description = _("🗄 آرشیو بازیکنان انتخاب‌شده")

    def restore_selected(self, request, queryset):
        count = 0
        for player in queryset.filter(is_archived=True):
            player.is_archived    = False
            player.status         = Player.Status.APPROVED
            player.archived_at    = None
            player.archive_reason = ""
            player.save(update_fields=["is_archived", "status", "archived_at", "archive_reason"])
            if player.user:
                player.user.is_active = True
                player.user.is_player = True
                player.user.save(update_fields=["is_active", "is_player"])
            count += 1
        self.message_user(request, f"{count} بازیکن بازگردانی شد.")
    restore_selected.short_description = _("♻️ بازگردانی بازیکنان انتخاب‌شده")


# ════════════════════════════════════════════════════════════════════
#  TechnicalProfile Admin
# ════════════════════════════════════════════════════════════════════

class PlayerSoftTraitInline(admin.TabularInline):
    model           = PlayerSoftTrait
    extra           = 0
    fields          = ("trait_type", "score", "note", "evaluated_by")
    readonly_fields = ("evaluated_by",)


@admin.register(TechnicalProfile)
class TechnicalProfileAdmin(admin.ModelAdmin):
    list_display    = ("player", "shirt_number", "position", "skill_level", "is_two_footed")
    list_filter     = ("position", "skill_level", "is_two_footed")
    search_fields   = ("player__first_name", "player__last_name", "player__national_id")
    inlines         = [PlayerSoftTraitInline]
    readonly_fields = ("updated_by",)

    def save_model(self, request, obj, form, change):
        obj.updated_by = request.user
        super().save_model(request, obj, form, change)


@admin.register(SoftTraitType)
class SoftTraitTypeAdmin(admin.ModelAdmin):
    list_display    = ("name", "is_active", "created_by", "created_at")
    list_filter     = ("is_active",)
    search_fields   = ("name",)
    readonly_fields = ("created_by", "created_at")

    def save_model(self, request, obj, form, change):
        if not obj.pk:
            obj.created_by = request.user
        super().save_model(request, obj, form, change)


# ════════════════════════════════════════════════════════════════════
#  Coach & Category Admin
# ════════════════════════════════════════════════════════════════════

@admin.register(Coach)
class CoachAdmin(admin.ModelAdmin):
    list_display    = ("full_name", "phone", "degree", "category_count", "is_active")
    list_filter     = ("degree", "is_active")
    search_fields   = ("first_name", "last_name", "phone")
    readonly_fields = ("created_at",)

    def full_name(self, obj):   return f"{obj.first_name} {obj.last_name}"
    full_name.short_description = _("مربی")

    def category_count(self, obj): return obj.categories.count()
    category_count.short_description = _("رده ها")


class TrainingScheduleInline(admin.TabularInline):
    model  = TrainingSchedule
    extra  = 1
    fields = ("weekday", "start_time", "end_time", "location")


class CoachCategoryRateInline(admin.TabularInline):
    model  = CoachCategoryRate
    extra  = 0
    fields = ("coach", "session_rate", "is_active")


@admin.register(TrainingCategory)
class TrainingCategoryAdmin(admin.ModelAdmin):
    list_display      = ("name", "monthly_fee", "player_count", "coach_count", "is_active")
    list_filter       = ("is_active",)
    search_fields     = ("name",)
    inlines           = [TrainingScheduleInline, CoachCategoryRateInline]
    filter_horizontal = ("players",)
    readonly_fields   = ("created_at",)

    def player_count(self, obj):
        return obj.players.filter(is_archived=False).count()  # ← آرشیو‌شده‌ها حساب نمی‌شوند
    player_count.short_description = _("بازیکنان فعال")

    def coach_count(self, obj): return obj.coaches.count()
    coach_count.short_description = _("مربیان")


# ════════════════════════════════════════════════════════════════════
#  Financial Admin
# ════════════════════════════════════════════════════════════════════

@admin.register(PlayerInvoice)
class PlayerInvoiceAdmin(admin.ModelAdmin):
    list_display    = ("player", "category", "jalali_year", "jalali_month",
                       "final_amount", "status_badge", "paid_at")
    list_filter     = ("status", "category", ("created_at", JDateFieldListFilter))
    search_fields   = ("player__first_name", "player__last_name",
                       "player__national_id", "zarinpal_ref_id")
    readonly_fields = ("final_amount", "created_at", "updated_at",
                       "zarinpal_ref_id", "zarinpal_authority")
    actions         = ["mark_paid", "mark_debtor"]

    def status_badge(self, obj):
        colors = {"pending": "#ffc107", "paid": "#28a745",
                  "debtor": "#dc3545", "pending_confirm": "#17a2b8"}
        labels = {"pending": "در انتظار", "paid": "پرداخت‌شده",
                  "debtor": "بدهکار", "pending_confirm": "انتظار تأیید"}
        return format_html(
            '<span style="background:{};color:#fff;padding:2px 8px;border-radius:4px">{}</span>',
            colors.get(obj.status, "#999"), labels.get(obj.status, obj.status)
        )
    status_badge.short_description = _("وضعیت")

    def mark_paid(self, request, queryset):
        queryset.update(status=PlayerInvoice.PaymentStatus.PAID, paid_at=timezone.now(), confirmed_by=request.user)
    mark_paid.short_description = _("✅ علامت‌گذاری پرداخت‌شده")

    def mark_debtor(self, request, queryset):
        queryset.filter(status="pending").update(status=PlayerInvoice.PaymentStatus.DEBTOR)
    mark_debtor.short_description = _("⚠️ علامت‌گذاری بدهکار")


@admin.register(CoachSalary)
class CoachSalaryAdmin(admin.ModelAdmin):
    list_display    = ("coach", "category", "sessions_attended",
                       "session_rate", "final_amount", "status", "paid_at")
    list_filter     = ("status", "category")
    search_fields   = ("coach__first_name", "coach__last_name")
    readonly_fields = ("base_amount", "final_amount", "created_at")


@admin.register(ExpenseCategory)
class ExpenseCategoryAdmin(admin.ModelAdmin):
    list_display  = ("name", "is_active", "created_by", "created_at")
    list_filter   = ("is_active",)
    readonly_fields = ("created_by", "created_at")

    def save_model(self, request, obj, form, change):
        if not obj.pk:
            obj.created_by = request.user
        super().save_model(request, obj, form, change)


@admin.register(Expense)
class ExpenseAdmin(admin.ModelAdmin):
    list_display  = ("title", "category", "amount", "transaction_type", "date", "recorded_by")
    list_filter   = ("transaction_type", "category", ("date", JDateFieldListFilter))
    search_fields = ("title", "description")
    readonly_fields = ("recorded_by", "created_at")

    def save_model(self, request, obj, form, change):
        if not obj.pk:
            obj.recorded_by = request.user
        super().save_model(request, obj, form, change)


# ════════════════════════════════════════════════════════════════════
#  Attendance Admin
# ════════════════════════════════════════════════════════════════════

class SessionDateInline(admin.TabularInline):
    model   = SessionDate
    extra   = 0
    fields  = ("date", "session_number", "notes")
    ordering = ("date",)


@admin.register(AttendanceSheet)
class AttendanceSheetAdmin(admin.ModelAdmin):
    list_display    = ("category", "jalali_year", "jalali_month",
                       "session_count", "is_finalized")
    list_filter     = ("is_finalized", "category", "jalali_year")
    readonly_fields = ("finalized_at", "finalized_by", "created_at")
    inlines         = [SessionDateInline]
    actions         = ["finalize_sheets"]

    def session_count(self, obj): return obj.session_dates.count()
    session_count.short_description = _("جلسات")

    def finalize_sheets(self, request, queryset):
        for s in queryset.filter(is_finalized=False):
            s.is_finalized = True
            s.finalized_at = timezone.now()
            s.finalized_by = request.user
            s.save(update_fields=["is_finalized", "finalized_at", "finalized_by"])
    finalize_sheets.short_description = _("✅ نهایی کردن")


# ════════════════════════════════════════════════════════════════════
#  Comms & Exercises Admin
# ════════════════════════════════════════════════════════════════════

@admin.register(Announcement)
class AnnouncementAdmin(admin.ModelAdmin):
    list_display      = ("title", "author", "is_pinned", "published_at")
    list_filter       = ("is_pinned", ("published_at", JDateFieldListFilter))
    search_fields     = ("title", "body")
    filter_horizontal = ("categories",)
    readonly_fields   = ("published_at",)

    def save_model(self, request, obj, form, change):
        if not obj.pk:
            obj.author = request.user
        super().save_model(request, obj, form, change)


@admin.register(Notification)
class NotificationAdmin(admin.ModelAdmin):
    list_display    = ("recipient", "type", "title", "is_read", "created_at")
    list_filter     = ("type", "is_read", ("created_at", JDateFieldListFilter))
    search_fields   = ("recipient__username", "title", "message")
    readonly_fields = ("created_at", "read_at")

    actions = ["mark_read"]
    def mark_read(self, request, queryset):
        queryset.update(is_read=True, read_at=timezone.now())
    mark_read.short_description = _("✅ خوانده‌شده")


@admin.register(Exercise)
class ExerciseAdmin(admin.ModelAdmin):
    list_display      = ("title", "media_type", "uploaded_by", "is_public", "created_at")
    list_filter       = ("media_type", "is_public", "categories")
    search_fields     = ("title", "description")
    filter_horizontal = ("categories", "tags")
    readonly_fields   = ("created_at", "updated_at")


@admin.register(ExerciseTag)
class ExerciseTagAdmin(admin.ModelAdmin):
    search_fields = ("name",)


@admin.register(PaymentLog)
class PaymentLogAdmin(admin.ModelAdmin):
    list_display    = ("invoice", "authority", "amount", "result", "created_at")
    list_filter     = ("result",)
    readonly_fields = ("invoice", "authority", "ref_id", "amount", "result",
                       "ip_address", "created_at", "verified_at", "raw_response")

    def has_add_permission(self, request):    return False
    def has_delete_permission(self, request, obj=None): return request.user.is_superuser
