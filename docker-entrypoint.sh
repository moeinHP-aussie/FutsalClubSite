#!/bin/bash
# ══════════════════════════════════════════════════════════════════
#  docker-entrypoint.sh  —  راه‌اندازی کانتینر Django
#  Runs migrations, collects static, waits for DB, then starts server
# ══════════════════════════════════════════════════════════════════

set -e   # خروج فوری در صورت خطا

echo "══════════════════════════════════════"
echo " 🚀 Futsal Club Management System"
echo " Starting container..."
echo "══════════════════════════════════════"

# ── Wait for PostgreSQL ───────────────────────────────────────────
echo "[1/5] انتظار برای آماده شدن PostgreSQL..."
max_retries=30
count=0
until python -c "
import os, django, sys
os.environ.setdefault('DJANGO_SETTINGS_MODULE', '${DJANGO_SETTINGS_MODULE}')
django.setup()
from django.db import connection
try:
    connection.ensure_connection()
    sys.exit(0)
except Exception:
    sys.exit(1)
" 2>/dev/null; do
    count=$((count + 1))
    if [ $count -ge $max_retries ]; then
        echo "❌ PostgreSQL پس از $max_retries تلاش در دسترس نیست. خروج."
        exit 1
    fi
    echo "   در انتظار PostgreSQL... (تلاش $count/$max_retries)"
    sleep 2
done
echo "✅ PostgreSQL آماده است."

# ── Run Migrations ────────────────────────────────────────────────
echo "[2/5] اجرای migrations..."
python manage.py migrate --no-input
echo "✅ Migrations اجرا شد."

# ── Collect Static Files ──────────────────────────────────────────
echo "[3/5] جمع‌آوری فایل‌های استاتیک..."
python manage.py collectstatic --no-input --clear
echo "✅ Static files جمع‌آوری شد."

# ── Compile Messages (i18n) ──────────────────────────────────────
if [ -d "locale" ]; then
    echo "[4/5] کامپایل پیام‌های ترجمه..."
    python manage.py compilemessages 2>/dev/null || true
else
    echo "[4/5] پوشه locale یافت نشد، رد شد."
fi

# ── Create Superuser (first time only) ───────────────────────────
echo "[5/5] بررسی superuser..."
python manage.py shell -c "
from django.contrib.auth import get_user_model
User = get_user_model()
import os
username = os.environ.get('DJANGO_SUPERUSER_USERNAME', 'admin')
if not User.objects.filter(username=username).exists():
    User.objects.create_superuser(
        username   = username,
        password   = os.environ.get('DJANGO_SUPERUSER_PASSWORD', 'Admin@1234'),
        first_name = 'مدیر',
        last_name  = 'سیستم',
        is_technical_director = True,
        is_finance_manager    = True,
    )
    print(f'✅ Superuser \"{username}\" ایجاد شد.')
else:
    print(f'ℹ️ Superuser \"{username}\" از قبل وجود دارد.')
" 2>/dev/null || true

echo ""
echo "══════════════════════════════════════"
echo " ✅ آماده‌سازی کامل شد."
echo " 🌐 سرور در حال راه‌اندازی..."
echo "══════════════════════════════════════"
echo ""

# ── Start the passed command (gunicorn / celery / etc.) ──────────
exec "$@"
