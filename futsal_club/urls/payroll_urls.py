"""
futsal_club/urls/payroll_urls.py   ←  نسخه v3 (کامل با همه ماژول‌های مالی)
namespace = "payroll"
"""
from django.urls import path

from ..views.finance_views import (
    # داشبورد
    FinanceDashboardV2View,

    # شهریه و فاکتور
    TuitionCategoryListView,
    InvoiceListView,
    GenerateMonthlyInvoicesView,
    GenerateAllCategoryInvoicesView,
    ConfirmInvoicePaymentView,
    InvoiceStatusUpdateView,
    SendPaymentReminderView,
    PlayerPaymentStatusView,
    PendingReceiptsView,
    PlayerInvoicesView,

    # حقوق مربیان
    SalaryListView,
    BulkSalaryCalculateView,
    CoachSalaryCalculateView,
    ApproveSalaryView,
    MarkSalaryPaidView,
    CoachConfirmSalaryView,

    # فاکتور دستی (کارکنان)
    StaffInvoiceListView,
    StaffInvoiceCreateView,
    StaffInvoiceReceiptUploadView,
    RecipientConfirmInvoiceView,
    StaffInvoiceCancelView,

    # تاریخچه مالی
    MyFinancialHistoryView,
    FinanceAllHistoryView,

    # هزینه‌ها
    ExpenseListView,
    ExpenseCreateView,
    ExpenseCategoryCreateView,
    ExpenseCategoryListView,

    # نرخ مربیان
    CoachRateManageView,

    # حضور و غیاب (نمای مالی)
    FinanceAttendanceCatsView,
    FinanceAttendanceSheetView,
    FinanceSessionDetailView,
)

from ..views.zarinpal_views import (
    InvoicePaymentInitView,
    ZarinpalCallbackView,
    PaymentSuccessView,
)

app_name = "payroll"

urlpatterns = [

    # ── داشبورد مالی ─────────────────────────────────────────────────────────
    path("dashboard/",
         FinanceDashboardV2View.as_view(), name="finance-dashboard"),

    # ── شهریه / فاکتور بازیکنان ──────────────────────────────────────────────
    path("tuition/",
         TuitionCategoryListView.as_view(), name="tuition-categories"),

    path("invoices/category/<int:category_pk>/",
         InvoiceListView.as_view(), name="invoice-list"),

    path("invoices/generate/<int:category_pk>/",
         GenerateMonthlyInvoicesView.as_view(), name="invoice-generate"),

    path("invoices/generate-all/",
         GenerateAllCategoryInvoicesView.as_view(), name="invoice-generate-all"),

    path("invoices/<int:invoice_pk>/confirm/",
         ConfirmInvoicePaymentView.as_view(), name="invoice-confirm"),

    path("invoices/<int:invoice_pk>/status/",
         InvoiceStatusUpdateView.as_view(), name="invoice-status-update"),

    path("invoices/send-reminder/",
         SendPaymentReminderView.as_view(), name="send-reminder"),

    # ── وضعیت پرداخت بازیکنان ────────────────────────────────────────────────
    path("player-payment-status/",
         PlayerPaymentStatusView.as_view(), name="player-payment-status"),

    # ── فاکتورهای در انتظار تأیید ────────────────────────────────────────────
    path("pending-receipts/",
         PendingReceiptsView.as_view(), name="pending-receipts"),

    # ── فاکتورهای خود بازیکن ─────────────────────────────────────────────────
    path("my-invoices/",
         PlayerInvoicesView.as_view(), name="player-invoices"),

    # ── درگاه پرداخت زرین‌پال ────────────────────────────────────────────────
    path("invoices/<int:invoice_pk>/pay/",
         InvoicePaymentInitView.as_view(), name="invoice-pay"),

    path("zarinpal/callback/",
         ZarinpalCallbackView.as_view(), name="zarinpal-callback"),

    path("invoices/<int:category_pk>/payment-success/",
         PaymentSuccessView.as_view(), name="payment-success"),

    # ── حقوق مربیان ──────────────────────────────────────────────────────────
    path("salary/category/<int:category_pk>/",
         SalaryListView.as_view(), name="salary-list"),

    path("salary/category/<int:category_pk>/bulk/",
         BulkSalaryCalculateView.as_view(), name="salary-bulk"),

    path("salary/coach/<int:coach_pk>/category/<int:category_pk>/",
         CoachSalaryCalculateView.as_view(), name="salary-calculate"),

    path("salary/<int:salary_pk>/approve/",
         ApproveSalaryView.as_view(), name="salary-approve"),

    path("salary/<int:salary_pk>/pay/",
         MarkSalaryPaidView.as_view(), name="salary-pay"),

    path("salary/<int:salary_pk>/confirm/",
         CoachConfirmSalaryView.as_view(), name="coach-confirm-salary"),

    # خلاصه حقوق مربی (نام مستعار به تاریخچه مالی)
    path("my-salary/",
         MyFinancialHistoryView.as_view(), name="coach-payroll-summary"),

    # ── نرخ مربیان ───────────────────────────────────────────────────────────
    path("coach-rates/",
         CoachRateManageView.as_view(), name="coach-rate-manage"),

    # ── فاکتور دستی کارکنان ──────────────────────────────────────────────────
    path("staff-invoices/",
         StaffInvoiceListView.as_view(), name="staff-invoice-list"),

    path("staff-invoices/create/",
         StaffInvoiceCreateView.as_view(), name="staff-invoice-create"),

    path("staff-invoices/<int:invoice_pk>/receipt/",
         StaffInvoiceReceiptUploadView.as_view(), name="staff-invoice-receipt"),

    path("staff-invoices/<int:invoice_pk>/confirm/",
         RecipientConfirmInvoiceView.as_view(), name="staff-invoice-confirm"),

    path("staff-invoices/<int:invoice_pk>/cancel/",
         StaffInvoiceCancelView.as_view(), name="staff-invoice-cancel"),

    # ── تاریخچه مالی ─────────────────────────────────────────────────────────
    path("my-financial-history/",
         MyFinancialHistoryView.as_view(), name="my-financial-history"),

    path("all-financial-history/",
         FinanceAllHistoryView.as_view(), name="all-financial-history"),

    # ── هزینه‌ها و درآمدها ────────────────────────────────────────────────────
    path("expenses/",
         ExpenseListView.as_view(), name="expense-list"),

    path("expenses/create/",
         ExpenseCreateView.as_view(), name="expense-create"),

    path("expenses/categories/",
         ExpenseCategoryListView.as_view(), name="expense-category-list"),

    path("expenses/categories/create/",
         ExpenseCategoryCreateView.as_view(), name="expense-category-create"),

    # ── حضور و غیاب (نمای مالی) ──────────────────────────────────────────────
    path("attendance/",
         FinanceAttendanceCatsView.as_view(), name="finance-attendance-cats"),

    path("attendance/category/<int:category_pk>/",
         FinanceAttendanceSheetView.as_view(), name="finance-attendance-sheet"),

    path("attendance/session/<int:session_pk>/",
         FinanceSessionDetailView.as_view(), name="finance-session-detail"),
]