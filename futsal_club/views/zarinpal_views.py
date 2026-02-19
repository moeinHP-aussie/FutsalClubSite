"""
views/zarinpal_views.py
─────────────────────────────────────────────────────────────────────
درگاه پرداخت زرین‌پال
Zarinpal payment gateway integration for PlayerInvoice.

Flow:
  1. Player clicks "Pay" → InvoicePaymentInitView → redirect to Zarinpal
  2. Zarinpal redirects back  → ZarinpalCallbackView → verify → mark paid
"""

from __future__ import annotations

import logging
from decimal import Decimal

import requests
from django.conf import settings
from django.contrib import messages
from django.contrib.auth.mixins import LoginRequiredMixin
from django.http import HttpResponse
from django.shortcuts import get_object_or_404, redirect
from django.urls import reverse
from django.utils import timezone
from django.views import View

from ..models import PaymentLog, PlayerInvoice

logger = logging.getLogger(__name__)

# ── Zarinpal API endpoints ────────────────────────────────────────
# Sandbox (آزمایشی)
ZP_REQUEST_URL  = "https://sandbox.zarinpal.com/pg/v4/payment/request.json"
ZP_VERIFY_URL   = "https://sandbox.zarinpal.com/pg/v4/payment/verify.json"
ZP_STARTPAY_URL = "https://sandbox.zarinpal.com/pg/StartPay/{authority}"

# Production (واقعی) — فعال‌سازی در تنظیمات production
# ZP_REQUEST_URL  = "https://api.zarinpal.com/pg/v4/payment/request.json"
# ZP_VERIFY_URL   = "https://api.zarinpal.com/pg/v4/payment/verify.json"
# ZP_STARTPAY_URL = "https://www.zarinpal.com/pg/StartPay/{authority}"

ZP_MERCHANT_ID  = getattr(settings, "ZARINPAL_MERCHANT_ID", "XXXXXXXX-XXXX-XXXX-XXXX-XXXXXXXXXXXX")
ZP_CURRENCY     = "IRT"   # تومان


# ────────────────────────────────────────────────────────────────────
#  Helper: تبدیل ریال به تومان
# ────────────────────────────────────────────────────────────────────
def rial_to_toman(amount: Decimal) -> int:
    return max(int(amount) // 10, 1000)   # حداقل ۱۰۰۰ تومان


# ────────────────────────────────────────────────────────────────────
#  View 1: شروع پرداخت
# ────────────────────────────────────────────────────────────────────
class InvoicePaymentInitView(LoginRequiredMixin, View):
    """
    ایجاد درخواست پرداخت برای یک فاکتور و ریدایرکت به صفحه زرین‌پال.

    POST  /payroll/invoices/<pk>/pay/
    """
    http_method_names = ["get", "post"]

    def get(self, request, invoice_pk: int):
        """صفحه تأیید قبل از ریدایرکت به درگاه."""
        invoice = self._get_invoice(request, invoice_pk)
        if isinstance(invoice, HttpResponse):
            return invoice
        return self._render_confirm(request, invoice)

    def post(self, request, invoice_pk: int):
        invoice = self._get_invoice(request, invoice_pk)
        if isinstance(invoice, HttpResponse):
            return invoice

        if invoice.status == PlayerInvoice.PaymentStatus.PAID:
            messages.info(request, "این فاکتور قبلاً پرداخت شده است.")
            return redirect("payroll:invoice-list", category_pk=invoice.category_id)

        # ── ساخت callback URL ─────────────────────────────────────
        callback_url = request.build_absolute_uri(
            reverse("payroll:zarinpal-callback")
        )

        amount_toman = rial_to_toman(invoice.final_amount)

        # ── درخواست به Zarinpal ───────────────────────────────────
        payload = {
            "merchant_id":   ZP_MERCHANT_ID,
            "amount":        amount_toman,
            "currency":      ZP_CURRENCY,
            "callback_url":  callback_url,
            "description":   f"شهریه {invoice.jalali_month_display()} — {invoice.player}",
            "metadata": {
                "invoice_id":  str(invoice.pk),
                "player_name": str(invoice.player),
            },
        }

        try:
            response  = requests.post(ZP_REQUEST_URL, json=payload, timeout=15)
            resp_data = response.json()
        except requests.RequestException as e:
            logger.error("Zarinpal request timeout/error: %s", e)
            messages.error(request, "ارتباط با درگاه پرداخت برقرار نشد. لطفاً مجدداً تلاش کنید.")
            return redirect("payroll:invoice-list", category_pk=invoice.category_id)

        code = resp_data.get("data", {}).get("code")
        authority = resp_data.get("data", {}).get("authority", "")

        if code != 100 or not authority:
            error_msg = resp_data.get("errors", {}).get("message", "خطای ناشناخته")
            logger.error("Zarinpal init failed: code=%s  msg=%s", code, error_msg)

            # ثبت لاگ شکست
            PaymentLog.objects.create(
                invoice=invoice,
                authority=authority or f"FAILED-{invoice.pk}",
                amount=invoice.final_amount,
                result=PaymentLog.PaymentResult.FAILED,
                ip_address=self._get_ip(request),
                raw_response=resp_data,
            )
            messages.error(request, f"خطا در اتصال به درگاه: {error_msg}")
            return redirect("payroll:invoice-list", category_pk=invoice.category_id)

        # ── ذخیره authority در فاکتور و لاگ ─────────────────────
        invoice.zarinpal_authority = authority
        invoice.save(update_fields=["zarinpal_authority"])

        PaymentLog.objects.create(
            invoice=invoice,
            authority=authority,
            amount=invoice.final_amount,
            result=PaymentLog.PaymentResult.INITIATED,
            ip_address=self._get_ip(request),
            raw_response=resp_data,
        )

        logger.info("Zarinpal payment initiated: invoice=%s authority=%s", invoice.pk, authority)

        # ── ریدایرکت به صفحه پرداخت ─────────────────────────────
        return redirect(ZP_STARTPAY_URL.format(authority=authority))

    # ── Helpers ───────────────────────────────────────────────────
    def _get_invoice(self, request, invoice_pk: int):
        invoice = get_object_or_404(PlayerInvoice, pk=invoice_pk)
        # بررسی دسترسی: فاکتور باید متعلق به بازیکن یا مدیر مالی باشد
        if (
            not request.user.is_finance_manager
            and not request.user.is_technical_director
            and not request.user.is_superuser
        ):
            if not (
                hasattr(request.user, "player_profile")
                and invoice.player == request.user.player_profile
            ):
                messages.error(request, "دسترسی غیرمجاز.")
                return redirect("dashboard")
        return invoice

    @staticmethod
    def _get_ip(request) -> str:
        x_forward = request.META.get("HTTP_X_FORWARDED_FOR")
        if x_forward:
            return x_forward.split(",")[0].strip()
        return request.META.get("REMOTE_ADDR", "")

    @staticmethod
    def _render_confirm(request, invoice):
        from django.shortcuts import render
        return render(request, "payroll/payment_confirm.html", {
            "invoice":       invoice,
            "amount_toman":  rial_to_toman(invoice.final_amount),
        })


# ────────────────────────────────────────────────────────────────────
#  View 2: بازگشت از درگاه (Callback)
# ────────────────────────────────────────────────────────────────────
class ZarinpalCallbackView(View):
    """
    پردازش بازگشت کاربر از درگاه پرداخت زرین‌پال.
    GET  /payroll/zarinpal/callback/?Authority=...&Status=OK|NOK

    این view باید بدون نیاز به لاگین باشد
    (کاربر ممکن است session منقضی شده داشته باشد).
    """

    def get(self, request):
        authority = request.GET.get("Authority", "")
        status    = request.GET.get("Status", "")

        # ── پیدا کردن فاکتور از طریق authority ──────────────────
        log = PaymentLog.objects.filter(authority=authority).select_related("invoice").first()
        if not log:
            logger.warning("Zarinpal callback: authority not found: %s", authority)
            messages.error(request, "تراکنش یافت نشد.")
            return redirect("dashboard")

        invoice = log.invoice

        # ── کاربر پرداخت را لغو کرد ──────────────────────────────
        if status != "OK":
            log.result       = PaymentLog.PaymentResult.CANCELED
            log.raw_response = {"Status": status, "Authority": authority}
            log.save(update_fields=["result", "raw_response"])

            messages.warning(request, "پرداخت توسط شما لغو شد.")
            return self._redirect_to_invoice(invoice)

        # ── تأیید تراکنش با API زرین‌پال ─────────────────────────
        amount_toman = rial_to_toman(invoice.final_amount)
        verify_payload = {
            "merchant_id": ZP_MERCHANT_ID,
            "amount":      amount_toman,
            "authority":   authority,
        }

        try:
            verify_resp = requests.post(ZP_VERIFY_URL, json=verify_payload, timeout=15)
            verify_data = verify_resp.json()
        except requests.RequestException as e:
            logger.error("Zarinpal verify timeout: %s", e)
            # تراکنش در حالت نامشخص — لاگ کن و به مدیر مالی اطلاع بده
            log.result       = PaymentLog.PaymentResult.FAILED
            log.raw_response = {"error": str(e)}
            log.save(update_fields=["result", "raw_response"])
            messages.error(request, "خطا در تأیید پرداخت. با پشتیبانی تماس بگیرید.")
            return self._redirect_to_invoice(invoice)

        code   = verify_data.get("data", {}).get("code")
        ref_id = str(verify_data.get("data", {}).get("ref_id", ""))

        # ── تأیید موفق ────────────────────────────────────────────
        if code in (100, 101):   # 101 = قبلاً تأیید شده (idempotent)
            log.result      = PaymentLog.PaymentResult.SUCCESS
            log.ref_id      = ref_id
            log.verified_at = timezone.now()
            log.raw_response = verify_data
            log.save(update_fields=["result", "ref_id", "verified_at", "raw_response"])

            # به‌روزرسانی فاکتور
            invoice.status             = PlayerInvoice.PaymentStatus.PAID
            invoice.paid_at            = timezone.now()
            invoice.zarinpal_ref_id    = ref_id
            invoice.zarinpal_authority = authority
            invoice.save(update_fields=[
                "status", "paid_at", "zarinpal_ref_id", "zarinpal_authority"
            ])

            logger.info(
                "Zarinpal payment SUCCESS: invoice=%s ref_id=%s amount=%s",
                invoice.pk, ref_id, amount_toman
            )
            messages.success(
                request,
                f"✅ پرداخت با موفقیت انجام شد. کد رهگیری: {ref_id}"
            )
            return self._redirect_success(invoice, ref_id)

        # ── تأیید ناموفق ──────────────────────────────────────────
        else:
            error_msg = verify_data.get("errors", {}).get("message", f"کد: {code}")
            log.result       = PaymentLog.PaymentResult.FAILED
            log.raw_response = verify_data
            log.save(update_fields=["result", "raw_response"])

            logger.warning("Zarinpal verify failed: code=%s msg=%s", code, error_msg)
            messages.error(request, f"پرداخت تأیید نشد: {error_msg}")
            return self._redirect_to_invoice(invoice)

    # ── Redirects ─────────────────────────────────────────────────
    @staticmethod
    def _redirect_to_invoice(invoice: PlayerInvoice):
        return redirect("payroll:invoice-list", category_pk=invoice.category_id)

    @staticmethod
    def _redirect_success(invoice: PlayerInvoice, ref_id: str):
        return redirect(
            f"/payroll/invoices/{invoice.category_id}/payment-success/"
            f"?ref={ref_id}&invoice={invoice.pk}"
        )


# ══════════════════════════════════════════════════════════════════
#  PaymentSuccessView
#  صفحه موفقیت پرداخت — بعد از verify موفق توسط ZarinpalCallbackView
#  URL: /payroll/invoices/<category_pk>/payment-success/?ref=...&invoice=...
# ══════════════════════════════════════════════════════════════════

from django.views.generic import TemplateView


class PaymentSuccessView(LoginRequiredMixin, TemplateView):
    template_name = "payroll/payment_success.html"
    login_url     = "/auth/login/"

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)

        category_pk = self.kwargs.get("category_pk")
        invoice_pk  = self.request.GET.get("invoice")
        ref_id      = self.request.GET.get("ref", "")

        from ..models import TrainingCategory
        ctx["category"] = get_object_or_404(TrainingCategory, pk=category_pk)

        invoice = None
        if invoice_pk:
            try:
                invoice = PlayerInvoice.objects.select_related(
                    "player__user", "category"
                ).get(pk=invoice_pk)
            except PlayerInvoice.DoesNotExist:
                pass

        ctx["invoice"] = invoice
        ctx["ref_id"]  = ref_id
        ctx["amount"]  = invoice.amount if invoice else None
        return ctx