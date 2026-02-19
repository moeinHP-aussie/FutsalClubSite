"""
tests/test_excel_import.py
─────────────────────────────────────────────────────────────────────
Unit tests for ExcelImportService — no Django DB required for parsing tests.
Run with:  python -m pytest tests/test_excel_import.py -v
"""
from __future__ import annotations

import datetime
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import pytest

from futsal_club.services.excel_import_service import (
    jalali_to_gregorian,
    normalise_national_id,
    normalise_phone,
    detect_insurance,
    map_education,
    map_hand_foot,
    safe_int,
    safe_decimal,
    InsuranceInfo,
)


# ════════════════════════════════════════════════════════════════════
#  Jalali → Gregorian
# ════════════════════════════════════════════════════════════════════

class TestJalaliConversion:

    def test_standard_slash_format(self):
        result = jalali_to_gregorian("1389/09/01")
        assert result == datetime.date(2010, 11, 22)

    def test_persian_digits(self):
        result = jalali_to_gregorian("۱۳۹۰/۰۱/۲۸")
        assert result == datetime.date(2011, 4, 17)

    def test_dash_separator(self):
        result = jalali_to_gregorian("1390-01-28")
        assert result == datetime.date(2011, 4, 17)

    def test_compact_8_digit(self):
        result = jalali_to_gregorian("13920422")
        assert result == datetime.date(2013, 7, 13)

    def test_another_real_date(self):
        result = jalali_to_gregorian("1393/06/25")
        assert result == datetime.date(2014, 9, 16)

    def test_none_returns_none(self):
        assert jalali_to_gregorian(None) is None

    def test_empty_string_returns_none(self):
        assert jalali_to_gregorian("") is None

    def test_nan_string_returns_none(self):
        assert jalali_to_gregorian("nan") is None

    def test_float_nan_returns_none(self):
        import math
        assert jalali_to_gregorian(float("nan")) is None

    def test_invalid_month_returns_none(self):
        assert jalali_to_gregorian("1390/13/01") is None

    def test_already_gregorian_date(self):
        d = datetime.date(2021, 5, 15)
        assert jalali_to_gregorian(d) == d

    def test_unusual_year_returns_none(self):
        assert jalali_to_gregorian("1250/01/01") is None   # too old

    @pytest.mark.parametrize("raw,expected", [
        ("1392/11/19", datetime.date(2014, 2, 8)),
        ("1393/01/25", datetime.date(2014, 4, 14)),
        ("1393/02/03", datetime.date(2014, 4, 23)),
        ("1393/04/11", datetime.date(2014, 7, 2)),
    ])
    def test_parametrized_dates(self, raw, expected):
        assert jalali_to_gregorian(raw) == expected


# ════════════════════════════════════════════════════════════════════
#  National ID
# ════════════════════════════════════════════════════════════════════

class TestNationalId:

    def test_valid_10_digit(self):
        assert normalise_national_id("0919697345") == "0919697345"

    def test_leading_zero_preserved(self):
        assert normalise_national_id("0044181868") == "0044181868"

    def test_scientific_notation_from_excel(self):
        # Excel sometimes shows 4581000000 as 4.581E+9
        result = normalise_national_id("4.581E+09")
        assert result == "4581000000"

    def test_persian_digits(self):
        result = normalise_national_id("۰۹۱۹۶۹۷۳۴۵")
        assert result == "0919697345"

    def test_none_returns_none(self):
        assert normalise_national_id(None) is None

    def test_too_short_returns_none(self):
        assert normalise_national_id("12345") is None

    def test_13_digit_returns_none(self):
        # 13-digit numbers seen in screenshot are likely errors
        assert normalise_national_id("0919697345419") is None

    def test_zero_padding_short_id(self):
        # 9-digit ID should be padded to 10
        result = normalise_national_id("919697345")
        assert result == "0919697345"


# ════════════════════════════════════════════════════════════════════
#  Phone
# ════════════════════════════════════════════════════════════════════

class TestPhoneNormalise:

    def test_standard_11_digit(self):
        assert normalise_phone("09157737387") == "09157737387"

    def test_10_digit_add_zero(self):
        assert normalise_phone("9157737387") == "09157737387"

    def test_international_format(self):
        assert normalise_phone("989157737387") == "09157737387"

    def test_persian_digits(self):
        assert normalise_phone("۰۹۱۵۷۷۳۷۳۸۷") == "09157737387"

    def test_none_returns_empty(self):
        assert normalise_phone(None) == ""


# ════════════════════════════════════════════════════════════════════
#  Insurance Detection
# ════════════════════════════════════════════════════════════════════

class TestInsuranceDetection:

    def test_future_date_no_colour_is_active(self):
        # A date far in the future should be active
        info = detect_insurance("1410/01/01", None)
        assert info.status == "active"
        assert info.expiry_date is not None

    def test_red_fill_no_date_is_expired(self):
        info = detect_insurance(None, "FFFF0000")
        assert info.status == "expired"
        assert info.expiry_date is None

    def test_yellow_fill_with_past_date_is_expired(self):
        # Past date overrides yellow fill
        info = detect_insurance("1390/01/01", "FFFFFF00")
        assert info.status == "expired"

    def test_no_fill_no_date_is_none(self):
        info = detect_insurance(None, None)
        assert info.status == "none"

    def test_green_fill_no_date(self):
        info = detect_insurance(None, "FF00FF00")
        assert info.status == "active"

    def test_empty_string_value(self):
        info = detect_insurance("", None)
        assert info.status == "none"


# ════════════════════════════════════════════════════════════════════
#  Education Mapping
# ════════════════════════════════════════════════════════════════════

class TestEducationMapping:

    @pytest.mark.parametrize("raw,expected", [
        ("دیپلم",           "high_school"),
        ("لیسانس",          "bachelor"),
        ("کارشناسی",        "bachelor"),
        ("کارشناسی ارشد",   "master"),
        ("فوق لیسانس",      "master"),
        ("سیکل",            "middle"),
        ("فوق دیپلم",       "associate"),
        ("دکترا",           "phd"),
        ("نظامی",           "other"),
        (None,              ""),
    ])
    def test_mapping(self, raw, expected):
        assert map_education(raw) == expected


# ════════════════════════════════════════════════════════════════════
#  Hand / Foot Preference
# ════════════════════════════════════════════════════════════════════

class TestHandFoot:

    def test_right(self):
        assert map_hand_foot("راست") == "R"

    def test_left(self):
        assert map_hand_foot("چپ") == "L"

    def test_none_defaults_right(self):
        assert map_hand_foot(None) == "R"

    def test_empty_defaults_right(self):
        assert map_hand_foot("") == "R"


# ════════════════════════════════════════════════════════════════════
#  Safe Numeric Conversions
# ════════════════════════════════════════════════════════════════════

class TestNumericConversions:

    def test_safe_int_normal(self):
        assert safe_int("175") == 175
        assert safe_int(175) == 175

    def test_safe_int_none(self):
        assert safe_int(None) is None

    def test_safe_int_persian(self):
        assert safe_int("۱۷۵") == 175

    def test_safe_decimal_normal(self):
        from decimal import Decimal
        assert safe_decimal("70.5") == Decimal("70.5")

    def test_safe_decimal_none(self):
        assert safe_decimal(None) is None


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
