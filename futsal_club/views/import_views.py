"""
views/import_views.py
─────────────────────────────────────────────────────────────────────
ایمپورت دسته‌جمعی بازیکنان از اکسل
Bulk Excel Import View — Technical Director only
"""
from __future__ import annotations

import json
import logging
import os
from pathlib import Path

from django.contrib import messages
from django.contrib.auth.mixins import LoginRequiredMixin
from django.core.files.storage import default_storage
from django.http import JsonResponse
from django.utils import timezone
from django.views import View
from django.views.generic import TemplateView

from ..mixins import RoleRequiredMixin
from ..services.excel_import_service import ExcelImportService, ImportResult

logger = logging.getLogger(__name__)

ALLOWED_EXTENSIONS = {".xlsx", ".xls"}
MAX_UPLOAD_MB      = 50


class BulkImportView(LoginRequiredMixin, RoleRequiredMixin, TemplateView):
    """
    صفحه اصلی ایمپورت دسته‌جمعی.
    GET  → نمایش فرم آپلود
    POST → پردازش فایل + نمایش نتیجه
    """
    allowed_roles = ["is_technical_director"]
    template_name = "registration/bulk_import.html"
    http_method_names = ["get", "post"]

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx.update({
            "max_upload_mb":    MAX_UPLOAD_MB,
            "allowed_formats":  ", ".join(ALLOWED_EXTENSIONS),
            "column_map":       _COLUMN_GUIDE,
        })
        return ctx

    def post(self, request, *args, **kwargs):
        uploaded = request.FILES.get("excel_file")

        # ── Validation ────────────────────────────────────────────
        if not uploaded:
            messages.error(request, "هیچ فایلی آپلود نشده است.")
            return self.get(request)

        suffix = Path(uploaded.name).suffix.lower()
        if suffix not in ALLOWED_EXTENSIONS:
            messages.error(request, f"فرمت فایل پشتیبانی نمی‌شود. فقط: {', '.join(ALLOWED_EXTENSIONS)}")
            return self.get(request)

        size_mb = uploaded.size / (1024 * 1024)
        if size_mb > MAX_UPLOAD_MB:
            messages.error(request, f"حجم فایل ({size_mb:.1f} MB) بیشتر از {MAX_UPLOAD_MB} MB است.")
            return self.get(request)

        # ── Save temporarily ──────────────────────────────────────
        tmp_name = f"imports/tmp_{timezone.now().strftime('%Y%m%d_%H%M%S')}_{uploaded.name}"
        tmp_path = default_storage.save(tmp_name, uploaded)
        full_path = default_storage.path(tmp_path)

        # ── Parse requested sheets ────────────────────────────────
        sheet_names_raw = request.POST.get("sheet_names", "").strip()
        sheet_names = [s.strip() for s in sheet_names_raw.split(",") if s.strip()] or None

        dry_run = request.POST.get("dry_run") == "1"

        # ── Run import ────────────────────────────────────────────
        try:
            svc    = ExcelImportService(filepath=full_path, sheet_names=sheet_names)
            result = svc.run(created_by=request.user, dry_run=dry_run)
        except Exception as exc:
            logger.exception("Import failed for %s", uploaded.name)
            messages.error(request, f"خطا در پردازش فایل: {exc}")
            _cleanup(full_path)
            return self.get(request)
        finally:
            _cleanup(full_path)

        # ── Log import ────────────────────────────────────────────
        _log_import(request.user, uploaded.name, result, dry_run)

        ctx = self.get_context_data()
        ctx.update({
            "result":    result,
            "filename":  uploaded.name,
            "dry_run":   dry_run,
        })

        if dry_run:
            messages.info(request, f"[پیش‌نمایش] {result.total_rows} ردیف تحلیل شد.")
        else:
            messages.success(
                request,
                f"ایمپورت کامل شد: {result.created} ایجاد | "
                f"{result.updated} به‌روز | {result.errors} خطا"
            )

        return self.render_to_response(ctx)


class ImportSheetPreviewView(LoginRequiredMixin, RoleRequiredMixin, View):
    """
    AJAX: Return sheet names from an uploaded file.
    POST with multipart form data: excel_file → JSON list of sheet names
    """
    allowed_roles     = ["is_technical_director"]
    http_method_names = ["post"]

    def post(self, request):
        uploaded = request.FILES.get("excel_file")
        if not uploaded:
            return JsonResponse({"error": "فایل ارسال نشد"}, status=400)

        suffix = Path(uploaded.name).suffix.lower()
        if suffix not in ALLOWED_EXTENSIONS:
            return JsonResponse({"error": "فرمت نامعتبر"}, status=400)

        tmp_name = f"imports/preview_{timezone.now().strftime('%Y%m%d_%H%M%S')}_{uploaded.name}"
        tmp_path = default_storage.save(tmp_name, uploaded)
        full_path = default_storage.path(tmp_path)

        try:
            import pandas as pd
            xf     = pd.ExcelFile(full_path)
            sheets = xf.sheet_names
            return JsonResponse({"sheets": sheets})
        except Exception as exc:
            return JsonResponse({"error": str(exc)}, status=500)
        finally:
            _cleanup(full_path)


# ── Helpers ───────────────────────────────────────────────────────────

def _cleanup(path: str):
    try:
        if os.path.exists(path):
            os.remove(path)
    except OSError:
        pass


def _log_import(user, filename: str, result: ImportResult, dry_run: bool):
    verb = "[DRY RUN]" if dry_run else "[IMPORT]"
    logger.info(
        "%s %s by %s: total=%d created=%d updated=%d skipped=%d errors=%d cats=%d",
        verb, filename, user,
        result.total_rows, result.created, result.updated,
        result.skipped, result.errors, result.categories_created,
    )


# ── Column Guide (for template) ────────────────────────────────────────
_COLUMN_GUIDE = [
    ("A", "ردیف",              "—", False),
    ("B", "نام",               "first_name", True),
    ("C", "نام خانوادگی",      "last_name", True),
    ("D", "نام پدر",           "father_name", True),
    ("E", "تاریخ تولد",        "dob (Jalali → Gregorian)", True),
    ("F", "شماره ملی",         "national_id ← کلید یکتا", True),
    ("G", "همراه بازیکن",      "phone", False),
    ("H", "همراه پدر",         "father_phone", False),
    ("I", "همراه مادر",        "mother_phone", False),
    ("J", "اعتبار بیمه",       "insurance_status + insurance_expiry_date (رنگ + تاریخ)", False),
    ("K", "سطح فنی",           "TechnicalProfile.skill_level", False),
    ("L", "رده سنی",           "— (display only)", False),
    ("M", "دسته تمرینی",       "TrainingCategory.name (auto-create)", False),
    ("N", "فرم ثبت نام",       "— (informational)", False),
    ("O", "تحصیلات پدر",       "father_education", False),
    ("P", "تحصیلات مادر",      "mother_education", False),
    ("Q", "شغل پدر",           "father_job", False),
    ("R", "شغل مادر",          "mother_job", False),
    ("S", "قد",                "height (cm)", False),
    ("T", "وزن",               "weight (kg)", False),
    ("U", "دست",               "preferred_hand (راست=R / چپ=L)", False),
    ("V", "پا",                "preferred_foot (راست=R / چپ=L)", False),
]
