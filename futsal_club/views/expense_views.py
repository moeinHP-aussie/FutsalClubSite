"""
futsal_club/views/expense_views.py
─────────────────────────────────────────────────────────────────────
مدیریت هزینه‌ها و درآمدها
"""
from decimal import Decimal

from django import forms
from django.contrib import messages
from django.contrib.auth.mixins import LoginRequiredMixin
from django.db.models import Q, Sum
from django.shortcuts import redirect
from django.urls import reverse_lazy
from django.views.generic import CreateView, ListView, TemplateView

import jdatetime

from ..mixins import RoleRequiredMixin
from ..models import Expense, ExpenseCategory


# ──────────────────────────────────────────────────────────────────
#  Mixin دسترسی مالی
# ──────────────────────────────────────────────────────────────────
class FinanceAccessMixin(LoginRequiredMixin, RoleRequiredMixin):
    allowed_roles = ["is_finance_manager", "is_technical_director"]


# ──────────────────────────────────────────────────────────────────
#  لیست هزینه‌ها
# ──────────────────────────────────────────────────────────────────
class ExpenseListView(FinanceAccessMixin, ListView):
    model               = Expense
    template_name       = "payroll/expense_list.html"
    context_object_name = "expenses"
    paginate_by         = 30

    def get_queryset(self):
        qs = Expense.objects.select_related("category", "recorded_by").order_by("-date", "-created_at")

        q    = self.request.GET.get("q", "").strip()
        cat  = self.request.GET.get("cat", "")
        kind = self.request.GET.get("kind", "")

        if q:
            qs = qs.filter(Q(title__icontains=q) | Q(description__icontains=q))
        if cat:
            qs = qs.filter(category__pk=cat)
        if kind in ("expense", "income"):
            qs = qs.filter(transaction_type=kind)
        return qs

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx["categories"] = ExpenseCategory.objects.all().order_by("name")
        ctx["q"]          = self.request.GET.get("q", "")
        ctx["cat_filter"] = self.request.GET.get("cat", "")
        ctx["kind_filter"]= self.request.GET.get("kind", "")

        # آمار خلاصه
        base = Expense.objects.all()
        ctx["total_expense"] = base.filter(transaction_type="expense").aggregate(s=Sum("amount"))["s"] or 0
        ctx["total_income"]  = base.filter(transaction_type="income" ).aggregate(s=Sum("amount"))["s"] or 0
        ctx["balance"]       = ctx["total_income"] - ctx["total_expense"]
        return ctx


# ──────────────────────────────────────────────────────────────────
#  فرم ثبت هزینه / درآمد
# ──────────────────────────────────────────────────────────────────
class ExpenseForm(forms.ModelForm):
    # تاریخ شمسی به‌صورت متن
    date_jalali = forms.CharField(
        label="تاریخ (شمسی)",
        widget=forms.TextInput(attrs={"placeholder": "مثال: ۱۴۰۳/۰۶/۱۵", "dir": "ltr"}),
        required=True,
    )

    class Meta:
        model  = Expense
        fields = ["category", "title", "amount", "transaction_type", "description", "attachment"]
        widgets = {
            "title":       forms.TextInput(attrs={"placeholder": "عنوان تراکنش"}),
            "amount":      forms.NumberInput(attrs={"placeholder": "مبلغ به ریال", "min": "0"}),
            "description": forms.Textarea(attrs={"rows": 3, "placeholder": "شرح اختیاری"}),
        }
        labels = {
            "category":         "دسته",
            "title":            "عنوان",
            "amount":           "مبلغ (ریال)",
            "transaction_type": "نوع تراکنش",
            "description":      "شرح",
            "attachment":       "پیوست (اختیاری)",
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # اگه تاریخ قبلاً set بود، به شمسی تبدیل کن
        if self.instance and self.instance.pk and self.instance.date:
            try:
                jd = jdatetime.date.fromgregorian(date=self.instance.date)
                self.fields["date_jalali"].initial = jd.strftime("%Y/%m/%d")
            except Exception:
                pass
        # category خالی اضافه کن
        if not ExpenseCategory.objects.exists():
            self.fields["category"].required = False

    def clean_date_jalali(self):
        raw = self.cleaned_data.get("date_jalali", "").strip()
        # تبدیل اعداد فارسی به انگلیسی
        for fa, en in zip("۰۱۲۳۴۵۶۷۸۹", "0123456789"):
            raw = raw.replace(fa, en)
        try:
            parts = [int(p) for p in raw.replace("-", "/").split("/")]
            jd    = jdatetime.date(*parts)
            return jd.togregorian()
        except Exception:
            raise forms.ValidationError("تاریخ وارد‌شده معتبر نیست. فرمت: ۱۴۰۳/۰۶/۱۵")


class ExpenseCreateView(FinanceAccessMixin, CreateView):
    model         = Expense
    form_class    = ExpenseForm
    template_name = "payroll/expense_form.html"
    success_url   = reverse_lazy("payroll:expense-list")

    def form_valid(self, form):
        obj = form.save(commit=False)
        obj.date        = form.cleaned_data["date_jalali"]
        obj.recorded_by = self.request.user
        obj.save()
        kind_label = "هزینه" if obj.transaction_type == "expense" else "درآمد"
        messages.success(self.request, f"{kind_label} «{obj.title}» با موفقیت ثبت شد.")
        return redirect(self.success_url)

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx["has_categories"] = ExpenseCategory.objects.exists()
        return ctx