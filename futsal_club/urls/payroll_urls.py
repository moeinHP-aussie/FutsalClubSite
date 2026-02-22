"""
futsal_club/urls/payroll_urls.py   ←  نسخه v2 (کامل)
namespace = "payroll"

تغییر نسبت به نسخه قبل:
  + اضافه شدن URL   invoices/<category_pk>/payment-success/
"""
from django.urls import path

from ..views.payroll_views import (
    ApproveSalaryView,
    BulkSalaryCalculateView,
    CoachSalaryCalculateView,
    ConfirmInvoicePaymentView,
    FinanceDashboardView,
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
    PaymentSuccessView,          # ← اضافه شد
)

from ..views.coach_payroll_view import CoachPayrollSummaryView, PayCoachSalaryView
from ..views.expense_views import (
    ExpenseListView, ExpenseCreateView,
    ExpenseCategoryCreateView, ExpenseCategoryListView,
)

app_name = "payroll"

urlpatterns = [
    # ── داشبورد مالی ──────────────────────────────────────────────
    path("dashboard/",
         FinanceDashboardView.as_view(), name="finance-dashboard"),

    # ── حقوق مربیان ───────────────────────────────────────────────
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

    # ── فاکتورهای بازیکنان ────────────────────────────────────────
    path("invoices/category/<int:category_pk>/",
         InvoiceListView.as_view(), name="invoice-list"),
    path("invoices/generate/<int:category_pk>/",
         GenerateMonthlyInvoicesView.as_view(), name="invoice-generate"),
    path("invoices/generate-all/",
         GenerateAllCategoryInvoicesView.as_view(), name="invoice-generate-all"),
    path("invoices/<int:invoice_pk>/confirm/",
         ConfirmInvoicePaymentView.as_view(), name="invoice-confirm"),
    path("invoices/<int:invoice_pk>/receipt/",
         UploadReceiptView.as_view(), name="invoice-receipt"),

    # ── درگاه پرداخت زرین‌پال ─────────────────────────────────────
    path("invoices/<int:invoice_pk>/pay/",
         InvoicePaymentInitView.as_view(), name="invoice-pay"),
    path("zarinpal/callback/",
         ZarinpalCallbackView.as_view(), name="zarinpal-callback"),

    # ── صفحه موفقیت پرداخت (ریدایرکت از ZarinpalCallbackView) ────
    path("invoices/<int:category_pk>/payment-success/",
         PaymentSuccessView.as_view(), name="payment-success"),

    # ── خلاصه حقوق مربیان ─────────────────────────────────────────
    path("coach-payroll/",
         CoachPayrollSummaryView.as_view(), name="coach-payroll-summary"),
    path("coach-payroll/pay/",
         PayCoachSalaryView.as_view(),      name="coach-payroll-pay"),

    # ── هزینه‌ها و درآمدها ─────────────────────────────────────────
    path("expenses/",
         ExpenseListView.as_view(),         name="expense-list"),
    path("expenses/create/",
         ExpenseCreateView.as_view(),        name="expense-create"),
    path("expenses/categories/",
         ExpenseCategoryListView.as_view(),  name="expense-category-list"),
    path("expenses/categories/create/",
         ExpenseCategoryCreateView.as_view(),name="expense-category-create"),
]