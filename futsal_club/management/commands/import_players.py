"""
management/commands/import_players.py
─────────────────────────────────────────────────────────────────────
دستور مدیریت برای ایمپورت بازیکنان از خط فرمان
Usage:
    python manage.py import_players /path/to/players.xlsx
    python manage.py import_players /path/to/players.xlsx --dry-run
    python manage.py import_players /path/to/players.xlsx --sheets "آموزشی 90-93,پایگانی"
"""
from __future__ import annotations

import sys
from pathlib import Path

from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand, CommandError

from futsal_club.services.excel_import_service import ExcelImportService


User = get_user_model()


class Command(BaseCommand):
    help = "ایمپورت دسته‌جمعی بازیکنان از فایل اکسل"

    def add_arguments(self, parser):
        parser.add_argument(
            "filepath",
            type=str,
            help="مسیر فایل اکسل (.xlsx/.xls)",
        )
        parser.add_argument(
            "--dry-run",
            action="store_true",
            default=False,
            help="پردازش بدون ذخیره در دیتابیس (پیش‌نمایش)",
        )
        parser.add_argument(
            "--sheets",
            type=str,
            default="",
            help='نام شیت‌ها جداشده با کاما (پیش‌فرض: همه شیت‌ها)  مثال: "آموزشی 90-93,پایگانی"',
        )
        parser.add_argument(
            "--user",
            type=str,
            default="",
            help="نام کاربری که به عنوان created_by ثبت می‌شود",
        )
        parser.add_argument(
            "--verbose-errors",
            action="store_true",
            default=False,
            help="نمایش جزئیات تمام خطاها",
        )

    def handle(self, *args, **options):
        filepath = Path(options["filepath"])

        if not filepath.exists():
            raise CommandError(f"فایل یافت نشد: {filepath}")
        if filepath.suffix.lower() not in (".xlsx", ".xls"):
            raise CommandError(f"فرمت نامعتبر: {filepath.suffix}")

        sheet_names_raw = options.get("sheets", "").strip()
        sheet_names = [s.strip() for s in sheet_names_raw.split(",") if s.strip()] or None

        dry_run = options["dry_run"]

        # Resolve user
        created_by = None
        if options["user"]:
            try:
                created_by = User.objects.get(username=options["user"])
            except User.DoesNotExist:
                self.stderr.write(self.style.WARNING(
                    f"کاربر «{options['user']}» یافت نشد — ادامه بدون created_by"
                ))

        mode = self.style.WARNING("[DRY RUN]") if dry_run else self.style.SUCCESS("[LIVE]")
        self.stdout.write(f"\n{mode} ایمپورت از: {filepath}")
        if sheet_names:
            self.stdout.write(f"  شیت‌ها: {', '.join(sheet_names)}")
        self.stdout.write("")

        # Run import
        svc    = ExcelImportService(filepath=str(filepath), sheet_names=sheet_names)
        result = svc.run(created_by=created_by, dry_run=dry_run)

        # ── Summary ──────────────────────────────────────────────
        self.stdout.write("═" * 55)
        self.stdout.write(self.style.HTTP_INFO("  نتیجه ایمپورت"))
        self.stdout.write("═" * 55)
        self.stdout.write(f"  کل ردیف‌ها    : {result.total_rows}")
        self.stdout.write(self.style.SUCCESS(f"  ایجاد شده     : {result.created}"))
        self.stdout.write(self.style.HTTP_REDIRECT(f"  به‌روز شده    : {result.updated}"))
        self.stdout.write(f"  رد شده        : {result.skipped}")
        self.stdout.write(self.style.ERROR(f"  خطا           : {result.errors}"))
        self.stdout.write(f"  دسته ایجادشده : {result.categories_created}")
        self.stdout.write(f"  موفقیت        : %{result.success_rate}")
        self.stdout.write("═" * 55)

        # ── Warnings ─────────────────────────────────────────────
        if result.warnings:
            self.stdout.write(self.style.WARNING("\n  هشدارها:"))
            for w in result.warnings:
                self.stdout.write(f"  ⚠  {w}")

        # ── Errors ───────────────────────────────────────────────
        error_rows = [r for r in result.rows if r.action == "error"]
        if error_rows:
            self.stdout.write(self.style.ERROR(f"\n  ردیف‌های خطا ({len(error_rows)}):"))
            show = error_rows if options["verbose_errors"] else error_rows[:10]
            for rr in show:
                self.stdout.write(
                    f"  ✕  شیت={rr.sheet}  ردیف={rr.row_num}  "
                    f"ملی={rr.national_id}  نام={rr.name}  "
                    f"پیام: {rr.message}"
                )
            if not options["verbose_errors"] and len(error_rows) > 10:
                self.stdout.write(
                    f"  ... و {len(error_rows) - 10} خطای دیگر "
                    f"(برای جزئیات کامل --verbose-errors اضافه کنید)"
                )

        self.stdout.write("")
        if result.errors > 0:
            sys.exit(1 if result.errors == result.total_rows else 0)
