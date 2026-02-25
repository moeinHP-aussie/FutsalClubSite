"""
futsal_club/urls/payroll_urls.py — نسخه v3 (کامل)
namespace = "payroll"
"""
from django.urls import path

from ..views.payroll_views import (
    ApproveSalaryView,
    BulkSalaryCalculateView,
    CoachSalaryCalculateView,
    ConfirmInvoicePaymentView,
    GenerateAllCategoryInvoicesView,
    GenerateMonthlyInvoicesView,
    InvoiceListView,
    MarkSalaryPaidView,
    SalaryListView,
    UploadReceiptView,
)
from ..views.zarinpal_views import (
    InvoicePaymentInitView,
    ZarinpalCallbackView,
    PaymentSuccessView,
)
from ..views.coach_payroll_view import CoachPayrollSummaryView, PayCoachSalaryView
from ..views.expense_views import (
    ExpenseListView, ExpenseCreateView,
    ExpenseCategoryCreateView, ExpenseCategoryListView,
)
from ..views.finance_views import (
    FinanceDashboardV2View,
    StaffInvoiceListView,
    StaffInvoiceCreateView,
    StaffInvoiceMarkPaidView,
    StaffInvoiceCancelView,
    MyFinancialHistoryView,
    FinanceAllHistoryView,
    InvoiceStatusUpdateView,
    BulkInvoiceStatusView,
    FinanceAttendanceCategoryListView,
    FinanceAttendanceSheetView,
    FinanceAttendanceSessionView,
    CoachRateManageView,
    PlayerPaymentStatusView,
)

app_name = "payroll"

urlpatterns = [
    path("dashboard/",
         FinanceDashboardV2View.as_view(),  name="finance-dashboard"),

    # حقوق مربیان
    path("salary/category/<int:category_pk>/",
         SalaryListView.as_view(),          name="salary-list"),
    path("salary/category/<int:category_pk>/bulk/",
         BulkSalaryCalculateView.as_view(), name="salary-bulk"),
    path("salary/coach/<int:coach_pk>/category/<int:category_pk>/",
         CoachSalaryCalculateView.as_view(),name="salary-calculate"),
    path("salary/<int:salary_pk>/approve/",
         ApproveSalaryView.as_view(),       name="salary-approve"),
    path("salary/<int:salary_pk>/pay/",
         MarkSalaryPaidView.as_view(),      name="salary-pay"),

    # فاکتور شهریه بازیکنان
    path("invoices/category/<int:category_pk>/",
         InvoiceListView.as_view(),         name="invoice-list"),
    path("invoices/generate/<int:category_pk>/",
         GenerateMonthlyInvoicesView.as_view(), name="invoice-generate"),
    path("invoices/generate-all/",
         GenerateAllCategoryInvoicesView.as_view(), name="invoice-generate-all"),
    path("invoices/<int:invoice_pk>/confirm/",
         ConfirmInvoicePaymentView.as_view(), name="invoice-confirm"),
    path("invoices/<int:invoice_pk>/receipt/",
         UploadReceiptView.as_view(),       name="invoice-receipt"),
    path("invoices/<int:invoice_pk>/status/",
         InvoiceStatusUpdateView.as_view(), name="invoice-status-update"),
    path("invoices/bulk-status/",
         BulkInvoiceStatusView.as_view(),   name="invoice-bulk-status"),

    # درگاه پرداخت
    path("invoices/<int:invoice_pk>/pay/",
         InvoicePaymentInitView.as_view(),  name="invoice-pay"),
    path("zarinpal/callback/",
         ZarinpalCallbackView.as_view(),    name="zarinpal-callback"),
    path("invoices/<int:category_pk>/payment-success/",
         PaymentSuccessView.as_view(),      name="payment-success"),

    # پرداخت حقوق مربیان
    path("coach-payroll/",
         CoachPayrollSummaryView.as_view(), name="coach-payroll-summary"),
    path("coach-payroll/pay/",
         PayCoachSalaryView.as_view(),      name="coach-payroll-pay"),

    # فاکتور دستی اعضاء
    path("staff-invoices/",
         StaffInvoiceListView.as_view(),    name="staff-invoice-list"),
    path("staff-invoices/create/",
         StaffInvoiceCreateView.as_view(),  name="staff-invoice-create"),
    path("staff-invoices/<int:invoice_pk>/paid/",
         StaffInvoiceMarkPaidView.as_view(),name="staff-invoice-paid"),
    path("staff-invoices/<int:invoice_pk>/cancel/",
         StaffInvoiceCancelView.as_view(),  name="staff-invoice-cancel"),

    # تاریخچه مالی
    path("my-history/",
         MyFinancialHistoryView.as_view(),  name="my-financial-history"),
    path("all-history/",
         FinanceAllHistoryView.as_view(),   name="all-financial-history"),

    # حضور و غیاب فقط‌خواندنی برای مدیر مالی
    path("attendance/",
         FinanceAttendanceCategoryListView.as_view(), name="finance-attendance-cats"),
    path("attendance/category/<int:category_pk>/",
         FinanceAttendanceSheetView.as_view(), name="finance-attendance-sheet"),
    path("attendance/session/<int:session_pk>/",
         FinanceAttendanceSessionView.as_view(), name="finance-session-detail"),

    # نرخ مربیان — فقط مدیر مالی
    path("coach-rates/",
         CoachRateManageView.as_view(),     name="coach-rate-manage"),

    # وضعیت پرداخت بازیکنان — مدیر فنی + مدیر مالی
    path("player-payments/",
         PlayerPaymentStatusView.as_view(), name="player-payment-status"),

    # هزینه‌ها
    path("expenses/",
         ExpenseListView.as_view(),         name="expense-list"),
    path("expenses/create/",
         ExpenseCreateView.as_view(),        name="expense-create"),
    path("expenses/categories/",
         ExpenseCategoryListView.as_view(),  name="expense-category-list"),
    path("expenses/categories/create/",
         ExpenseCategoryCreateView.as_view(),name="expense-category-create"),
]