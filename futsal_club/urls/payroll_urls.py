"""
futsal_club/urls/payroll_urls.py — نسخه v4 (بازسازی کامل)
namespace = "payroll"

ساختار ۶ بخش مالی:
  1. مدیریت شهریه
  2. حقوق مربیان
  3. رسیدهای در انتظار تأیید
  4. فاکتور دستی
  5. تاریخچه مالی کل
  6. هزینه‌ها و درآمدها
"""
from django.urls import path

from ..views.finance_views import (
    # داشبورد
    FinanceDashboardV2View,

    # 1. مدیریت شهریه
    TuitionCategoryListView,
    InvoiceListView,
    GenerateMonthlyInvoicesView,
    GenerateAllCategoryInvoicesView,
    ConfirmInvoicePaymentView,
    InvoiceStatusUpdateView,
    PlayerPaymentStatusView,
    PlayerInvoicesView,
    SendPaymentReminderView,

    # 2. رسیدهای در انتظار
    PendingReceiptsView,

    # 3. حقوق مربیان
    SalaryListView,
    BulkSalaryCalculateView,
    CoachSalaryCalculateView,
    ApproveSalaryView,
    MarkSalaryPaidView,
    CoachConfirmSalaryView,

    # 4. فاکتور دستی
    StaffInvoiceListView,
    StaffInvoiceCreateView,
    StaffInvoiceReceiptUploadView,
    RecipientConfirmInvoiceView,
    StaffInvoiceCancelView,

    # 5. تاریخچه مالی
    MyFinancialHistoryView,
    FinanceAllHistoryView,

    # 6. هزینه‌ها
    ExpenseListView,
    ExpenseCreateView,
    ExpenseCategoryCreateView,
    ExpenseCategoryListView,

    # ابزارها
    CoachRateManageView,
)

from ..views.coach_payroll_view import CoachPayrollSummaryView

from ..views.zarinpal_views import (
    InvoicePaymentInitView,
    ZarinpalCallbackView,
    PaymentSuccessView,
)

app_name = "payroll"

urlpatterns = [

    # ── داشبورد مرکزی ──────────────────────────────────────────────
    path("dashboard/",
         FinanceDashboardV2View.as_view(),       name="finance-dashboard"),

    # ══════════════════════════════════════════════════════════════
    # 1. مدیریت شهریه
    # ══════════════════════════════════════════════════════════════

    # لیست دسته‌های آموزشی با آمار شهریه
    path("tuition/",
         TuitionCategoryListView.as_view(),      name="tuition-categories"),

    # فاکتورهای یک دسته × ماه
    path("tuition/category/<int:category_pk>/",
         InvoiceListView.as_view(),               name="invoice-list"),

    # صدور فاکتور
    path("tuition/generate/<int:category_pk>/",
         GenerateMonthlyInvoicesView.as_view(),   name="invoice-generate"),
    path("tuition/generate-all/",
         GenerateAllCategoryInvoicesView.as_view(),name="invoice-generate-all"),

    # تأیید/رد رسید بازیکن
    path("tuition/invoice/<int:invoice_pk>/confirm/",
         ConfirmInvoicePaymentView.as_view(),     name="invoice-confirm"),
    path("tuition/invoice/<int:invoice_pk>/status/",
         InvoiceStatusUpdateView.as_view(),        name="invoice-status-update"),

    # وضعیت پرداخت همه بازیکنان
    path("tuition/payment-status/",
         PlayerPaymentStatusView.as_view(),       name="player-payment-status"),

    # ارسال یادآوری
    path("tuition/send-reminder/",
         SendPaymentReminderView.as_view(),        name="send-reminder"),

    # درگاه پرداخت آنلاین
    path("tuition/invoice/<int:invoice_pk>/pay/",
         InvoicePaymentInitView.as_view(),        name="invoice-pay"),
    path("zarinpal/callback/",
         ZarinpalCallbackView.as_view(),           name="zarinpal-callback"),
    path("tuition/invoice/<int:category_pk>/success/",
         PaymentSuccessView.as_view(),             name="payment-success"),

    # ── بازیکن: فاکتورهای من ─────────────────────────────────────
    path("my-invoices/",
         PlayerInvoicesView.as_view(),             name="player-invoices"),

    # ══════════════════════════════════════════════════════════════
    # 2. رسیدهای در انتظار تأیید
    # ══════════════════════════════════════════════════════════════
    path("pending-receipts/",
         PendingReceiptsView.as_view(),            name="pending-receipts"),

    # ══════════════════════════════════════════════════════════════
    # 3. حقوق مربیان
    # ══════════════════════════════════════════════════════════════
    path("salary/category/<int:category_pk>/",
         SalaryListView.as_view(),                 name="salary-list"),
    path("salary/category/<int:category_pk>/bulk/",
         BulkSalaryCalculateView.as_view(),        name="salary-bulk"),
    path("salary/coach/<int:coach_pk>/category/<int:category_pk>/",
         CoachSalaryCalculateView.as_view(),       name="salary-calculate"),
    path("salary/<int:salary_pk>/approve/",
         ApproveSalaryView.as_view(),              name="salary-approve"),
    path("salary/<int:salary_pk>/pay/",
         MarkSalaryPaidView.as_view(),             name="salary-pay"),
    path("salary/<int:salary_pk>/confirm/",
         CoachConfirmSalaryView.as_view(),         name="coach-confirm-salary"),
    # تعیین نرخ
    path("salary/coach-rates/",
         CoachRateManageView.as_view(),            name="coach-rate-manage"),

    path("coach-payroll/",
         CoachPayrollSummaryView.as_view(),  name="coach-payroll-summary"),

    # ══════════════════════════════════════════════════════════════
    # 4. فاکتور دستی
    # ══════════════════════════════════════════════════════════════
    path("staff-invoices/",
         StaffInvoiceListView.as_view(),           name="staff-invoice-list"),
    path("staff-invoices/create/",
         StaffInvoiceCreateView.as_view(),         name="staff-invoice-create"),
    path("staff-invoices/<int:invoice_pk>/receipt/",
         StaffInvoiceReceiptUploadView.as_view(),  name="staff-invoice-receipt"),
    path("staff-invoices/<int:invoice_pk>/confirm/",
         RecipientConfirmInvoiceView.as_view(),    name="staff-invoice-confirm"),
    path("staff-invoices/<int:invoice_pk>/cancel/",
         StaffInvoiceCancelView.as_view(),         name="staff-invoice-cancel"),

    # ══════════════════════════════════════════════════════════════
    # 5. تاریخچه مالی
    # ══════════════════════════════════════════════════════════════
    path("my-history/",
         MyFinancialHistoryView.as_view(),         name="my-financial-history"),
    path("all-history/",
         FinanceAllHistoryView.as_view(),          name="all-financial-history"),

    # ══════════════════════════════════════════════════════════════
    # 6. هزینه‌ها و درآمدها
    # ══════════════════════════════════════════════════════════════
    path("expenses/",
         ExpenseListView.as_view(),                name="expense-list"),
    path("expenses/create/",
         ExpenseCreateView.as_view(),              name="expense-create"),
    path("expenses/categories/",
         ExpenseCategoryListView.as_view(),        name="expense-category-list"),
    path("expenses/categories/create/",
         ExpenseCategoryCreateView.as_view(),      name="expense-category-create"),
]