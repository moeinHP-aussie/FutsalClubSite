"""
futsal_club/management/commands/generate_monthly_invoices.py
────────────────────────────────────────────────────────────────────
دستور مدیریت برای صدور خودکار فاکتورهای شهریه ماهانه بازیکنان.

استفاده:
  python manage.py generate_monthly_invoices          # ماه جاری
  python manage.py generate_monthly_invoices --year 1403 --month 9
  python manage.py generate_monthly_invoices --dry-run  # فقط پیش‌نمایش

زمان‌بندی (Cron/Task Scheduler):
  اجرا در روز آخر هر ماه ساعت ۲۳:۰۰
  
  Windows Task Scheduler:
    schtasks /create /tn "FutsalInvoice" /tr "python manage.py generate_monthly_invoices" /sc monthly ...
  
  Linux Cron:
    0 23 28-31 * * [ "$(date +\%d)" = "$(cal | awk 'NF{last=$NF}END{print last}')" ] && cd /path/project && python manage.py generate_monthly_invoices
"""

import logging

import jdatetime
from django.core.management.base import BaseCommand

from futsal_club.models import TrainingCategory
from futsal_club.services.payroll_service import PayrollService
from futsal_club.utils.jalali_utils import JalaliMonth

logger = logging.getLogger(__name__)


class Command(BaseCommand):
    help = "صدور خودکار فاکتور شهریه ماهانه برای تمام بازیکنان فعال"

    def add_arguments(self, parser):
        parser.add_argument("--year",  type=int, help="سال شمسی (پیش‌فرض: ماه جاری)")
        parser.add_argument("--month", type=int, help="ماه شمسی (پیش‌فرض: ماه جاری)")
        parser.add_argument("--category", type=int, help="فقط برای یک دسته خاص")
        parser.add_argument("--dry-run", action="store_true", help="فقط پیش‌نمایش بدون ذخیره")

    def handle(self, *args, **options):
        dry_run = options["dry_run"]

        # تعیین ماه
        if options["year"] and options["month"]:
            target_month = JalaliMonth(options["year"], options["month"])
        else:
            today  = jdatetime.date.today()
            target_month = JalaliMonth(today.year, today.month)

        self.stdout.write(
            self.style.WARNING(
                f"\n{'[DRY-RUN] ' if dry_run else ''}"
                f"صدور فاکتور ماه {target_month.year}/{target_month.month:02d}\n"
                f"{'─' * 50}"
            )
        )

        # انتخاب دسته‌ها
        if options["category"]:
            categories = TrainingCategory.objects.filter(pk=options["category"], is_active=True)
        else:
            categories = TrainingCategory.objects.filter(is_active=True)

        if not categories.exists():
            self.stdout.write(self.style.ERROR("هیچ دسته فعالی یافت نشد."))
            return

        total_created = 0
        total_skipped = 0
        total_errors  = 0

        for category in categories:
            player_count = category.players.filter(
                status="approved", is_archived=False
            ).count()

            self.stdout.write(f"  📚 {category.name}  ({player_count} بازیکن)")

            if dry_run:
                self.stdout.write(
                    self.style.NOTICE(f"      [DRY-RUN] {player_count} فاکتور صادر می‌شد")
                )
                total_created += player_count
                continue

            try:
                batch = PayrollService.generate_monthly_invoices(
                    category=category,
                    jalali_month=target_month,
                )
                total_created += batch.created_count
                total_skipped += batch.skipped_count
                total_errors  += batch.error_count

                status_line = (
                    f"      ✅ {batch.created_count} جدید"
                    f"  |  ⏭️  {batch.skipped_count} قبلاً موجود"
                )
                if batch.error_count:
                    status_line += f"  |  ❌ {batch.error_count} خطا"
                    for err in batch.errors:
                        self.stdout.write(
                            self.style.ERROR(f"         خطا: {err['player']} — {err['reason']}")
                        )
                self.stdout.write(status_line)

            except Exception as exc:
                logger.exception("خطا در صدور فاکتور دسته %s", category)
                self.stdout.write(self.style.ERROR(f"      ❌ خطای کلی: {exc}"))
                total_errors += 1

        # خلاصه نهایی
        self.stdout.write("\n" + "─" * 50)
        self.stdout.write(
            self.style.SUCCESS(
                f"✅ جمع‌بندی: {total_created} فاکتور صادر، "
                f"{total_skipped} رد شد، {total_errors} خطا"
            )
        )

        if dry_run:
            self.stdout.write(self.style.WARNING("  [DRY-RUN] هیچ تغییری ذخیره نشد."))
